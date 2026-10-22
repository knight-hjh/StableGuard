#!/usr/bin/env python3
"""Re-judge an existing StableGuard candidate log without invoking build systems.

This is used for same-candidate LLM reruns and prompt/component ablations when the
local Solidity build environment is not reproducible. It reads candidate
locations from a prior scan JSON directory, extracts source excerpts directly
from dataset files, then calls the StableGuard detection prompt in the selected
mode.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_realworld_validation_packet import find_source_file, function_line  # noqa: E402
from scan_c1c5 import add_usage  # noqa: E402
from stableguard.llm.client import LLMClient  # noqa: E402
from stableguard.llm.response_parser import parse_detection_response  # noqa: E402
from stableguard.stablecoin_specific.prompt import SYSTEM_PROMPT, build_prompt  # noqa: E402
from static_screening.lib.stablecoin_specific import SUBDEFECTS  # noqa: E402

load_dotenv()
logger.remove()
logger.add(sys.stderr, level="WARNING")


EXCERPT_BEFORE = int(os.getenv("RERUN_EXCERPT_BEFORE", "25"))
EXCERPT_AFTER = int(os.getenv("RERUN_EXCERPT_AFTER", "70"))


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", name).strip("_")


def candidate_from_dict(row: dict) -> SimpleNamespace:
    return SimpleNamespace(
        sub=str(row.get("sub") or ""),
        contract=str(row.get("contract") or ""),
        file=str(row.get("file") or ""),
        function=str(row.get("function") or ""),
        line=int(row.get("line") or 0),
        reason=str(row.get("reason") or ""),
        to_dict=lambda: dict(row),
    )


def read_excerpt(project: str, row: dict) -> tuple[str, str]:
    src = find_source_file(project, row.get("file"))
    if not src:
        return "", ""
    try:
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", str(src.relative_to(ROOT))
    line = int(row.get("line") or 0) or None
    center = line or function_line(lines, row.get("function")) or 1
    start = max(1, center - EXCERPT_BEFORE)
    end = min(len(lines), center + EXCERPT_AFTER)
    body = "\n".join(f"{i:5d}: {lines[i - 1]}" for i in range(start, end + 1))
    return body, str(src.relative_to(ROOT))


def input_rows(input_file: Path) -> list[dict]:
    data = json.loads(input_file.read_text(encoding="utf-8"))
    rows = data.get("all_verdicts") or []
    if rows:
        return rows
    return data.get("findings") or []


def run_project(input_file: Path, output_dir: Path, mode: str) -> dict:
    data = json.loads(input_file.read_text(encoding="utf-8"))
    project = data.get("project") or input_file.stem
    out = {
        "project": project,
        "status": "unknown",
        "source": str(input_file.relative_to(ROOT)),
        "rerun_mode": mode,
        "n_candidates": 0,
        "findings": [],
        "all_verdicts": [],
        "error": None,
    }
    rows = input_rows(input_file)
    out["n_candidates"] = len(rows)
    if not rows:
        out["status"] = "ok_no_candidates"
        return out

    llm = LLMClient()
    out["model"] = llm.model
    out["ablation_mode"] = mode
    for row in rows:
        cand = candidate_from_dict(row)
        code, source_path = read_excerpt(project, row)
        try:
            resp = llm.complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_prompt(cand, code, mode=mode)},
                ],
                max_tokens=900,
            )
            add_usage(out, resp)
            parsed = parse_detection_response(resp.content)
        except Exception as exc:
            out["all_verdicts"].append({
                **dict(row),
                "source_path": source_path,
                "defect_present": "error",
                "error": f"{type(exc).__name__}: {str(exc)[:160]}",
            })
            continue

        matched_sub = parsed.get("matches_subtype")
        if isinstance(matched_sub, str):
            matched_sub = matched_sub.strip().upper()
        if mode == "no_routing" and matched_sub in SUBDEFECTS:
            verdict_base = {**dict(row), "routed_sub": row.get("sub"), "sub": matched_sub}
        else:
            verdict_base = dict(row)
        verdict = {
            **verdict_base,
            "source_path": source_path,
            "defect_present": parsed.get("defect_present"),
            "confidence": parsed.get("confidence"),
            "severity": parsed.get("severity"),
        }
        out["all_verdicts"].append(verdict)
        if parsed.get("defect_present") is True:
            out["findings"].append({**verdict, "reasoning": parsed.get("reasoning")})

    out["status"] = "ok"
    return out


def worker(args: tuple[Path, Path, str]) -> dict:
    input_file, output_dir, mode = args
    project = json.loads(input_file.read_text(encoding="utf-8")).get("project") or input_file.stem
    output_file = output_dir / f"{safe_name(project)}.json"
    if output_file.exists():
        return {"project": project, "status": "skip"}
    try:
        out = run_project(input_file, output_dir, mode)
    except Exception as exc:
        out = {
            "project": project,
            "status": "crash",
            "rerun_mode": mode,
            "n_candidates": 0,
            "findings": [],
            "all_verdicts": [],
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
        }
    output_file.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "project": project,
        "status": out.get("status"),
        "cands": out.get("n_candidates", 0),
        "findings": len(out.get("findings", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="logs/c1c5_scan14")
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", default=os.getenv("ABLATION_MODE", "full"),
                        choices=["full", "no_facts", "no_routing", "no_grouped_agent"])
    parser.add_argument("projects", nargs="*")
    args = parser.parse_args()

    input_dir = ROOT / args.input
    output_dir = ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    input_files = sorted(input_dir.glob("*.json"))
    if args.projects:
        wanted = set(args.projects)
        input_files = [
            p for p in input_files
            if (json.loads(p.read_text(encoding="utf-8")).get("project") or p.stem) in wanted
        ]

    logger.warning(
        f"candidate rerun: {len(input_files)} projects from {input_dir} -> {output_dir} mode={args.mode}"
    )
    jobs = int(os.getenv("JOBS", "2"))
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = [ex.submit(worker, (p, output_dir, args.mode)) for p in input_files]
        for i, fut in enumerate(as_completed(futs), start=1):
            row = fut.result()
            logger.warning(
                f"[{i}/{len(futs)}] {row['project']} -> {row.get('status')} "
                f"cands={row.get('cands', '?')} findings={row.get('findings', '?')}"
            )
    logger.warning("candidate rerun complete.")


if __name__ == "__main__":
    main()
