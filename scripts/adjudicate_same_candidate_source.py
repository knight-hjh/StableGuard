#!/usr/bin/env python3
"""Source-grounded adjudication for same-candidate StableGuard reruns.

Positive-only benchmark precision is a lower bound. This script adjudicates
confirmed flags that do not directly match GT by showing an independent judge
the subtype definition, the flagged location, detector/model reasoning, and a
source excerpt. GT-matched flags are counted as true positives directly.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_stablecoin_specific import load_ground_truth, match, project_to_dir  # noqa: E402
from rerun_candidates_from_log import read_excerpt  # noqa: E402
from stableguard.llm.client import LLMClient  # noqa: E402
from stableguard.llm.response_parser import extract_json  # noqa: E402
from stableguard.stablecoin_specific.prompt import load_kb  # noqa: E402

load_dotenv()

JUDGE_SYS = """You are a skeptical senior smart-contract auditor.
You verify whether a flagged Solidity location genuinely matches a claimed stablecoin defect subtype.

Use TYPE/MECHANISM semantics, not exploitability-only semantics:
- genuine=true if the shown source structurally implements the claimed subtype mechanism at this location, even if a guard mitigates exploitation or the code is a patched variant.
- genuine=false if the source matches a different subtype, is generic/library/test/mock boilerplate, or the claimed mechanism is absent/keyword-only.

Base your judgment only on the subtype definition and the shown source excerpt.
Output strict JSON only: {"genuine": true|false, "why": "<brief source-grounded reason>"}."""

JUDGE_USR = """Subtype {sub} — {name}
Definition: {definition}
Must reject if: {negative}

Flagged location:
- project: {project}
- file: {file}
- contract: {contract}
- function: {function}
- line: {line}
- detector reason: {reason}
- model pattern_match: {pattern_match}
- model mechanism: {mechanism}

Source excerpt:
```solidity
{source}
```

Is this flag a genuine instance of subtype {sub}? Strict JSON only."""


def usage_add(out: dict, response) -> None:
    usage = response.usage
    bucket = out.setdefault("usage", {
        "model": usage.model,
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "elapsed_seconds": 0.0,
    })
    bucket["model"] = usage.model
    bucket["calls"] += 1
    bucket["prompt_tokens"] += usage.prompt_tokens
    bucket["completion_tokens"] += usage.completion_tokens
    bucket["total_tokens"] += usage.total_tokens
    bucket["elapsed_seconds"] = round(bucket["elapsed_seconds"] + usage.elapsed_seconds, 2)


def load_flags(scan_dir: Path) -> list[dict]:
    flags = []
    for path in sorted(scan_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        project = data.get("project") or path.stem
        ddir = project_to_dir(project) or project
        for row in data.get("findings", []) or []:
            flags.append({
                "dir": ddir,
                "project": project,
                "sub": row.get("sub") or row.get("subtype"),
                "file": row.get("file") or row.get("contract"),
                "raw": row,
            })
    return flags


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scan_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    scan_dir = args.scan_dir
    out_path = args.out or (scan_dir.parent / f"{scan_dir.name}_source_adjudicate.json")
    kb = load_kb()
    gt = load_ground_truth()
    flags = load_flags(scan_dir)

    matched_idx = {
        i for i, flag in enumerate(flags)
        if any(match(row, flag) for row in gt)
    }
    unmatched = [(i, flag) for i, flag in enumerate(flags) if i not in matched_idx]

    result = {
        "scan_dir": str(scan_dir),
        "total_flags": len(flags),
        "gt_matched_flags": len(matched_idx),
        "judged_flags": len(unmatched),
        "genuine_judged": 0,
        "spurious_judged": 0,
        "records": [],
    }
    print(
        f"flags={len(flags)} gt_matched={len(matched_idx)} to_judge={len(unmatched)}",
        flush=True,
    )

    llm = LLMClient()
    for n, (idx, flag) in enumerate(unmatched, start=1):
        raw = flag["raw"]
        sub = flag["sub"]
        entry = kb.get(sub, {})
        source, source_path = read_excerpt(flag["project"], raw)
        reasoning = raw.get("reasoning") or {}
        user = JUDGE_USR.format(
            sub=sub,
            name=entry.get("name", ""),
            definition=str(entry.get("definition", "")).strip(),
            negative="; ".join(entry.get("not_this_defect", []) or []),
            project=flag["project"],
            file=raw.get("file", ""),
            contract=raw.get("contract", ""),
            function=raw.get("function", ""),
            line=raw.get("line", ""),
            reason=str(raw.get("reason", ""))[:600],
            pattern_match=str(reasoning.get("pattern_match", ""))[:700],
            mechanism=str(reasoning.get("mechanism", ""))[:700],
            source=source[:6000] or "// source unavailable",
        )
        try:
            response = llm.complete(
                [{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}],
                max_tokens=260,
            )
            usage_add(result, response)
            parsed = extract_json(response.content) or {}
            genuine = parsed.get("genuine") is True
            why = str(parsed.get("why", ""))[:500]
            error = None
        except Exception as exc:
            genuine = False
            why = ""
            error = f"{type(exc).__name__}: {str(exc)[:180]}"

        if genuine:
            result["genuine_judged"] += 1
        else:
            result["spurious_judged"] += 1
        result["records"].append({
            "flag_index": idx,
            "project": flag["project"],
            "sub": sub,
            "file": raw.get("file", ""),
            "contract": raw.get("contract", ""),
            "function": raw.get("function", ""),
            "line": raw.get("line", ""),
            "source_path": source_path,
            "genuine": genuine,
            "why": why,
            "error": error,
        })
        if n % 10 == 0 or n == len(unmatched):
            tp = len(matched_idx) + result["genuine_judged"]
            print(f"[{n}/{len(unmatched)}] adjudicated_tp={tp}/{len(flags)}={tp/len(flags):.1%}", flush=True)

    tp = len(matched_idx) + result["genuine_judged"]
    result["adjudicated_tp"] = tp
    result["adjudicated_precision"] = tp / len(flags) if flags else None
    result["gt_only_precision_lower_bound"] = len(matched_idx) / len(flags) if flags else None

    by_sub_total = defaultdict(int)
    by_sub_gt = defaultdict(int)
    by_sub_genuine = defaultdict(int)
    by_sub_spurious = defaultdict(int)
    for i, flag in enumerate(flags):
        by_sub_total[flag["sub"]] += 1
        if i in matched_idx:
            by_sub_gt[flag["sub"]] += 1
    for row in result["records"]:
        if row["genuine"]:
            by_sub_genuine[row["sub"]] += 1
        else:
            by_sub_spurious[row["sub"]] += 1
    result["by_sub"] = {
        sub: {
            "total": by_sub_total[sub],
            "gt_matched": by_sub_gt[sub],
            "adjudicated_genuine": by_sub_genuine[sub],
            "adjudicated_spurious": by_sub_spurious[sub],
            "tp": by_sub_gt[sub] + by_sub_genuine[sub],
        }
        for sub in sorted(by_sub_total)
    }

    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"ADJUDICATED_PRECISION {tp}/{len(flags)} = {tp/len(flags):.1%}; "
        f"wrote {out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
