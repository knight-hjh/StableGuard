#!/usr/bin/env python3
"""Offline legacy recognition statistics; no LLM calls or strict-validity claims."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_stablecoin_specific import match


ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-dir", required=True, type=Path)
    parser.add_argument(
        "--labels", type=Path,
        default=ROOT / "dataset/instances.json",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.scan_dir.is_dir():
        parser.error("--scan-dir must be an existing per-project output directory")

    metadata = json.loads(args.labels.read_text(encoding="utf-8"))
    labels = metadata["rows"]
    if len(labels) != 65 or len({row["evaluation_id"] for row in labels}) != 65:
        parser.error("Expected the explicit 65-label cohort with unique evaluation IDs")
    expected_projects = {row["dir"] for row in labels}
    flags = []
    projects = {}
    ignored_files = []
    technical_errors = 0
    uncertain = 0
    unclassified = 0

    for path in sorted(args.scan_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("project") not in expected_projects:
            ignored_files.append(path.name)
            continue
        project = data["project"]
        if project in projects:
            parser.error(f"Multiple result files for project {project}; select one run")
        findings = data.get("findings", [])
        verdicts = data.get("all_verdicts", [])
        if not isinstance(findings, list) or not isinstance(verdicts, list):
            parser.error(f"Invalid per-project result structure in {path.name}")
        projects[project] = {
            "file": path.name,
            "status": data.get("status", "unknown"),
            "n_candidates": data.get("n_candidates"),
            "recorded_verdicts": len(verdicts),
        }
        for verdict in verdicts:
            state = verdict.get("defect_present")
            if state == "error":
                technical_errors += 1
            elif state == "uncertain":
                uncertain += 1
            elif type(state) is not bool:
                unclassified += 1
        for finding in findings:
            if finding.get("defect_present") is True:
                flags.append({
                    "dir": project,
                    "sub": finding.get("sub") or finding.get("subtype"),
                    "file": finding.get("file") or finding.get("contract"),
                    "raw": finding,
                })

    matches = {
        row["evaluation_id"]: [i for i, flag in enumerate(flags) if match(row, flag)]
        for row in labels
    }
    matched_alerts = {index for indices in matches.values() for index in indices}
    matched_labels = sum(bool(indices) for indices in matches.values())
    by_category = {}
    for category in sorted({row["macro"] for row in labels}):
        members = [row for row in labels if row["macro"] == category]
        detected = sum(bool(matches[row["evaluation_id"]]) for row in members)
        by_category[category] = {
            "matched_labels": detected,
            "total_labels": len(members),
            "legacy_recognition_recall": detected / len(members),
        }

    report = {
        "status": "LEGACY_RECOGNITION_ONLY",
        "matching_scope": metadata.get("scope"),
        "labels": len(labels),
        "matched_labels": matched_labels,
        "legacy_recognition_recall": matched_labels / len(labels),
        "positive_alerts": len(flags),
        "benchmark_matched_alerts": len(matched_alerts),
        "unmatched_alerts": [
            flag for i, flag in enumerate(flags) if i not in matched_alerts
        ],
        "label_to_alert_indices": matches,
        "by_category": by_category,
        "projects": projects,
        "missing_projects": sorted(expected_projects - set(projects)),
        "non_ok_projects": sorted(
            project for project, row in projects.items()
            if row["status"] not in {"ok", "ok_no_candidates"}
        ),
        "recorded_candidate_errors": technical_errors,
        "recorded_uncertain_candidates": uncertain,
        "unclassified_candidate_results": unclassified,
        "ignored_files": ignored_files,
        "strict_precision": None,
        "strict_f1": None,
        "limitations": [
            "Historical project/subtype/file-alias matching, not exact root validation",
            "Missing projects remain in the 65-label recognition denominator",
            "Technical failures are not classified as true negatives",
            "Unmatched alerts require source review; matches do not establish exploitability",
            "Recorded project success does not certify full compilation or request coverage",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({
        "matched_labels": matched_labels,
        "labels": len(labels),
        "legacy_recognition_recall": report["legacy_recognition_recall"],
        "missing_projects": report["missing_projects"],
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
