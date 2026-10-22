#!/usr/bin/env python3
"""Build a source-evidence packet for validating real-world candidate defects.

This packet is for type-correctness validation, not exploitability validation:
the question is whether the cited code location genuinely matches the reported
C1-C5/S01-S19 mechanism.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from eval_stablecoin_specific import project_to_dir  # noqa: E402
from stableguard.stablecoin_specific.prompt import load_kb  # noqa: E402

IN = ROOT / "logs" / "REALWORLD_new_defects.json"
OUT_DIR = ROOT / "paper" / "realworld_validation"
OUT_JSONL = OUT_DIR / "full_realworld_defect_validation_packet.jsonl"
OUT_CSV = OUT_DIR / "full_realworld_defect_validation_packet.csv"

EXCLUDE_DIRS = {
    "node_modules", "artifacts", "cache", ".git", "build", "dist", "out",
    "coverage", "typechain", "typechain-types", "test", "tests",
}


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_id(i: int) -> str:
    return f"RW-FULL-{i:03d}"


def find_source_file(project: str, file_name: str | None) -> Path | None:
    if not file_name:
        return None
    ddir = project_to_dir(project) or project
    root = ROOT / "dataset" / ddir
    if not root.is_dir():
        return None
    basename = Path(file_name).name.lower()
    matches: list[Path] = []
    for path in root.rglob(Path(file_name).name):
        rel_parts = {p.lower() for p in path.relative_to(root).parts}
        if rel_parts & EXCLUDE_DIRS:
            continue
        if path.name.lower() == basename and path.is_file():
            matches.append(path)
    if not matches:
        for path in root.rglob("*.sol"):
            rel_parts = {p.lower() for p in path.relative_to(root).parts}
            if rel_parts & EXCLUDE_DIRS:
                continue
            if path.name.lower() == basename:
                matches.append(path)
    if not matches:
        return None
    matches.sort(key=lambda p: (len(p.parts), str(p)))
    return matches[0]


def function_line(lines: list[str], function_name: str | None) -> int | None:
    if not function_name:
        return None
    fn = re.escape(function_name.strip())
    pat = re.compile(rf"\bfunction\s+{fn}\b|\b{fn}\s*\(")
    for i, line in enumerate(lines, start=1):
        if pat.search(line):
            return i
    return None


def excerpt(path: Path | None, line: int | None, function_name: str | None) -> tuple[str, int | None, int | None]:
    if not path or not path.is_file():
        return "", None, None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return "", None, None
    center = line if line and line > 0 else function_line(lines, function_name)
    if not center:
        center = 1
    start = max(1, center - 28)
    end = min(len(lines), center + 45)
    body = "\n".join(f"{i:5d}: {lines[i - 1]}" for i in range(start, end + 1))
    return body, start, end


def main() -> None:
    kb = load_kb()
    data = json.loads(IN.read_text(encoding="utf-8"))
    rows = []
    for i, defect in enumerate(data["defects"], start=1):
        sub = defect["sub"]
        entry = kb.get(sub, {})
        src = find_source_file(defect.get("project", ""), defect.get("file"))
        try:
            line = int(defect.get("line") or 0) or None
        except Exception:
            line = None
        code, start, end = excerpt(src, line, defect.get("function"))
        row = {
            "sample_id": safe_id(i),
            "project": defect.get("project", ""),
            "macro": defect.get("macro", ""),
            "sub": sub,
            "subtype_name": entry.get("name", ""),
            "subtype_definition": clean_text(entry.get("definition", "")),
            "not_this_defect": clean_text("; ".join(entry.get("not_this_defect", []) or [])),
            "file": defect.get("file", ""),
            "function": defect.get("function", ""),
            "line": defect.get("line", ""),
            "severity_tool": defect.get("severity", ""),
            "mechanism_tool": defect.get("mechanism", ""),
            "source_path": str(src.relative_to(ROOT)) if src else "",
            "excerpt_start": start or "",
            "excerpt_end": end or "",
            "code_excerpt": code,
        }
        rows.append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    fields = [
        "sample_id", "project", "macro", "sub", "subtype_name",
        "file", "function", "line", "severity_tool", "mechanism_tool",
        "source_path", "excerpt_start", "excerpt_end", "subtype_definition",
        "not_this_defect", "code_excerpt",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    found = sum(1 for row in rows if row["source_path"])
    print(json.dumps({
        "packet_jsonl": str(OUT_JSONL),
        "packet_csv": str(OUT_CSV),
        "n": len(rows),
        "source_found": found,
        "source_missing": len(rows) - found,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
