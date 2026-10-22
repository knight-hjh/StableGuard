#!/usr/bin/env python3
"""
Evaluation harness for the C1-C5 / S01-S19 stablecoin-specific taxonomy.

(1) Parses the labeled dataset `stablecoin_specific_full.csv` into structured ground
    truth: project (-> dataset dir), file, function, line-range, macro C, sub-type S,
    BugID, severity.
(2) Scores a hybrid-scan output dir (per-project JSON with confirmed findings tagged by
    sub-type) against that ground truth: per-S and overall RECALL + a PRECISION lower
    bound, plus leave-one-project-out.

Target (task_plan 新主线): per-type PRECISION > 90%.

Precision note: the dataset is POSITIVE-ONLY (71 known bugs), so a confirmed flag that
does NOT match a labeled bug may be a true-but-unlabeled defect OR a false positive. We
therefore report:
  - recall            = matched GT / total GT            (directly measurable)
  - precision_vs_gt   = matched confirmed / all confirmed (a LOWER bound on real precision)
and dump every unmatched confirmed flag to `<scan>/_adjudicate.json` for manual/LLM review;
real precision = TP/(TP+FP) after adjudicating those.

Usage:
  python3 scripts/eval_stablecoin_specific.py                 # print ground-truth summary
  python3 scripts/eval_stablecoin_specific.py <scan_dir>      # score a scan output dir
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
CSV = ROOT / "stablecoin_specific_full.csv"
DATASET = ROOT / "dataset" / "projects"

# CSV 项目 -> dataset/projects/ dir name (only the non-obvious ones need an entry).
PROJECT_DIR = {
    "MIM": "MIM",                       # Abracadabra MIM (GmOracle), NOT MIMATIC
    "CASH（Opus CASH）": "CASH（Opus CASH）",
}


def project_to_dir(proj: str) -> str | None:
    if proj in PROJECT_DIR and (DATASET / PROJECT_DIR[proj]).is_dir():
        return PROJECT_DIR[proj]
    if (DATASET / proj).is_dir():
        return proj
    base = proj.split("（")[0].split("(")[0].strip()
    if (DATASET / base).is_dir():
        return base
    cands = [d for d in os.listdir(DATASET) if d == base or d.startswith(base)]
    return cands[0] if cands else None


_INHERIT = {}
_INHERIT_FILE = {}  # dir -> {derived_file: set(all base-chain files), regardless of func}
try:
    _INHERIT = json.loads((ROOT / "logs" / "inherit_resolver.json").read_text())
    # file-level chain: a GT label at a DERIVED contract file should also credit a tool flag
    # at any base file in that contract's inheritance chain (evidence = the inheritance link),
    # even when the 位置 names no function. Derived from the existing file::func resolver.
    for ddir, rmap in _INHERIT.items():
        fm = defaultdict(set)
        for k, chain in rmap.items():
            derived = k.split("::", 1)[0]
            fm[derived] |= set(chain)
        _INHERIT_FILE[ddir] = {f: s for f, s in fm.items()}
except Exception:
    pass


def all_files_in(loc: str):
    """ALL source-file basenames mentioned in a location/description string. Many GT 位置
    fields list several files for one finding (the mechanism spans files) — accept any.
    Also map a bare `ContractName.func()` / `ContractName::func` (no .sol) to ContractName.sol,
    since auditors sometimes cite the contract, not the file."""
    out = [os.path.basename(x).lower()
           for x in re.findall(r"([\w./-]+\.(?:sol|cairo|ts|vy))", loc or "")]
    if not out:  # no explicit file -> infer contract names cited as Name.func()/Name::func
        for cn in re.findall(r"\b([A-Z]\w+)(?:\.\w+\s*\(|::)", loc or ""):
            out.append(f"{cn.lower()}.sol")
    return out


def parse_location(loc: str):
    """Best-effort split of the 位置 column -> (file_basename, function, (lo, hi)|None)."""
    loc = (loc or "").strip()
    m = re.search(r"([\w./-]+\.(?:sol|cairo|ts|vy))", loc)
    fname = os.path.basename(m.group(1)) if m else None
    func = None
    fm = re.search(r"(?:::|:)([A-Za-z_][\w]*)", loc)
    if fm:
        func = fm.group(1)
    lines = None
    lm = re.search(r"L?(\d+)\s*-\s*L?(\d+)", loc) or re.search(r"L(\d+)", loc)
    if lm:
        g = lm.groups()
        lines = (int(g[0]), int(g[1]) if len(g) > 1 and g[1] else int(g[0]))
    return fname, func, lines


def load_ground_truth():
    gt = []
    for r in csv.DictReader(open(CSV, encoding="utf-8")):
        macro = (r["大类"] or "").split()[0]          # "C5 面值..." -> "C5"
        sub = r["类型ID"].strip()                       # "S05"
        fname, func, lines = parse_location(r["位置"])
        # ALL files the GT 位置 names for this one finding (mechanism may span files).
        files = set(all_files_in(r["位置"]))
        if fname:
            files.add(fname.lower())
        # INHERITANCE EVIDENCE: a labeled function may be inherited — its code lives in a base
        # file. Expand acceptable files to the inheritance-chain files that implement that
        # function (from logs/inherit_resolver.json), so a tool flag at the base counts.
        ddir = project_to_dir(r["项目"].strip())
        rmap = _INHERIT.get(ddir, {})
        if func:
            for f in list(files):
                files |= set(rmap.get(f"{f}::{func}", []))
        # file-level inheritance: union base-chain files for each named derived file (no func needed)
        fmap = _INHERIT_FILE.get(ddir, {})
        for f in list(files):
            files |= fmap.get(f, set())
        gt.append({
            "bugid": r["BugID"].strip(),
            "project": r["项目"].strip(),
            "dir": project_to_dir(r["项目"].strip()),
            "macro": macro, "sub": sub,
            "severity": r["严重度"].strip(),
            "name": r["漏洞名称"].strip(),
            "loc_raw": r["位置"].strip(),
            "file": fname, "func": func, "lines": lines,
            "files": files,
        })
    return gt


def _norm_file(f):
    return os.path.basename(f).lower() if f else None


def match(gt_entry, flag):
    """A confirmed scan flag matches a GT entry: same dir + same sub-type + the flag's file is
    among ANY of the files the GT 位置 lists for that finding (mechanism may span files)."""
    if gt_entry["dir"] != flag.get("dir"):
        return False
    if gt_entry["sub"] != flag.get("sub"):
        return False
    gfiles = gt_entry.get("files") or ({_norm_file(gt_entry["file"])} if gt_entry.get("file") else set())
    ff = _norm_file(flag.get("file"))
    if gfiles and ff:
        return ff in gfiles
    return True  # if either side lacks a file, fall back to dir+sub match


def load_scan(scan_dir: Path):
    """Load confirmed flags from a scan output dir. Each per-project JSON is expected to
    carry findings/all_verdicts tagged with a `sub` (S-type) and `file`. Returns list of
    confirmed (defect_present==True) flags."""
    flags = []
    for f in scan_dir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text())
        proj = d.get("project") or f.stem
        ddir = project_to_dir(proj) or proj
        for v in d.get("findings", []) or []:
            flags.append({"dir": ddir, "sub": v.get("sub") or v.get("subtype"),
                          "file": v.get("file") or v.get("contract"),
                          "raw": v})
    return flags


def score(gt, flags, exclude_project=None):
    g = [e for e in gt if e["dir"] != exclude_project]
    f = [x for x in flags if x["dir"] != exclude_project]
    matched_gt, matched_flag = set(), set()
    for gi, ge in enumerate(g):
        for fi, fl in enumerate(f):
            if match(ge, fl):
                matched_gt.add(gi)
                matched_flag.add(fi)
    recall = len(matched_gt) / len(g) if g else 0.0
    prec = len(matched_flag) / len(f) if f else 0.0
    return {"n_gt": len(g), "n_flags": len(f), "matched_gt": len(matched_gt),
            "recall": recall, "precision_vs_gt": prec,
            "unmatched_flags": [f[i] for i in range(len(f)) if i not in matched_flag]}


def main():
    gt = load_ground_truth()
    miss = [e for e in gt if not e["dir"]]
    by_sub = defaultdict(int)
    by_proj = defaultdict(int)
    for e in gt:
        by_sub[e["sub"]] += 1
        by_proj[e["dir"] or e["project"]] += 1
    print(f"=== Ground truth: {len(gt)} findings, {len(by_proj)} projects "
          f"({len(miss)} unresolved dirs) ===")
    print("by project:", dict(sorted(by_proj.items(), key=lambda x: -x[1])))
    print("by sub-type:", dict(sorted(by_sub.items())))
    if miss:
        print("UNRESOLVED project dirs:", [(e["project"], e["bugid"]) for e in miss])
    # location parse coverage
    nofile = [e["bugid"] for e in gt if not e["file"]]
    print(f"location parse: file resolved for {len(gt)-len(nofile)}/{len(gt)}; "
          f"missing file for {nofile[:8]}{'...' if len(nofile)>8 else ''}")

    if len(sys.argv) > 1:
        scan_dir = Path(sys.argv[1])
        flags = load_scan(scan_dir)
        print(f"\n=== Scoring {scan_dir} ({len(flags)} confirmed flags) ===")
        overall = score(gt, flags)
        print(f"OVERALL: recall={overall['recall']:.1%} "
              f"({overall['matched_gt']}/{overall['n_gt']}) · "
              f"precision_vs_gt(lower bound)={overall['precision_vs_gt']:.1%} "
              f"({overall['n_flags']} flags)")
        # per sub-type recall
        print("\nper sub-type:")
        for s in sorted(by_sub):
            gs = [e for e in gt if e["sub"] == s]
            fs = [x for x in flags if x.get("sub") == s]
            r = score(gs, fs)
            print(f"  {s}: recall={r['recall']:.0%} ({r['matched_gt']}/{len(gs)}) "
                  f"prec_lb={r['precision_vs_gt']:.0%} flags={len(fs)}")
        # leave-one-project-out
        print("\nleave-one-project-out (recall on held-out project):")
        for p in sorted(by_proj):
            held = [e for e in gt if (e["dir"] or e["project"]) == p]
            heldf = [x for x in flags if x.get("dir") == p]
            r = score(held, heldf)
            print(f"  −{p}: recall={r['recall']:.0%} ({r['matched_gt']}/{len(held)})")
        # dump unmatched confirmed flags for adjudication (real precision = TP/(TP+FP)).
        # write next to the scan dir (its contents may be root-owned from docker).
        adj = scan_dir.parent / f"{scan_dir.name}_adjudicate.json"
        try:
            adj.write_text(json.dumps(overall["unmatched_flags"], indent=2, ensure_ascii=False))
        except PermissionError:
            adj = Path("/tmp") / f"{scan_dir.name}_adjudicate.json"
            adj.write_text(json.dumps(overall["unmatched_flags"], indent=2, ensure_ascii=False))
        print(f"\n[{len(overall['unmatched_flags'])} unmatched confirmed flags -> {adj} "
              f"for FP adjudication]")


if __name__ == "__main__":
    main()
