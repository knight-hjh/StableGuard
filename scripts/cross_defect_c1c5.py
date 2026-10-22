#!/usr/bin/env python3
"""Cross-defect COMPOSITION reasoning for the C1-C5 line.

Static rules (and the per-candidate LLM verdict) judge each defect in ISOLATION. This stage takes
the CONFIRMED defects that co-occur on the SAME contract and asks the LLM whether two or more of
them COMPOSE into a multi-step attack path that is materially worse than any single defect alone —
a capability static analysis cannot provide. Intended for real-world projects; here it also runs
on the labeled-dataset scans as a capability demo.

Input : a scan output dir (logs/c1c5_scan14) with per-project findings (each carries sub/file/
        function/reasoning.mechanism).
Output: logs/<OUT>/<project>.json with, per contract, the LLM's attack-path composition verdict.

Usage:  IN=logs/c1c5_scan14 OUT=logs/cross_defect python3 scripts/cross_defect_c1c5.py [PROJECT ...]
        MIN_SUBS=2  (only analyze contracts with >= this many DISTINCT sub-types)
"""
import json, os, re, sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()
from stableguard.llm.client import LLMClient
from stableguard.llm.response_parser import extract_json
from stableguard.stablecoin_specific.prompt import load_kb

IN = Path(os.getenv("IN", "logs/c1c5_scan14"))
OUT = Path(os.getenv("OUT", "logs/cross_defect")); OUT.mkdir(parents=True, exist_ok=True)
MIN_SUBS = int(os.getenv("MIN_SUBS", "2"))
GROUND = os.getenv("GROUND", "1") != "0"        # inject real function source (step 1)
PER_FN = int(os.getenv("PER_FN", "700"))        # max chars of source per defect function
PROJECT_PER_FN = int(os.getenv("PROJECT_PER_FN", "900"))
PROJECT_SOURCE_CAP = int(os.getenv("PROJECT_SOURCE_CAP", "12000"))
SOURCE_LOADER = os.getenv("SOURCE_LOADER", "compile")  # compile | filesystem | auto
CONTRACT_MAX_TOKENS = int(os.getenv("CONTRACT_MAX_TOKENS", "1100"))
PROJECT_MAX_TOKENS = int(os.getenv("PROJECT_MAX_TOKENS", "1300"))
JSON_MODE = os.getenv("JSON_MODE", "0") != "0"


def _source_candidates(project, finding):
    """Locate the source named by a finding without requiring project compilation."""
    root = Path("dataset") / project
    if not root.exists():
        return []
    raw_file = str(finding.get("file") or finding.get("contract") or "")
    basename = Path(raw_file).name
    if not basename.lower().endswith(".sol"):
        basename += ".sol"

    direct = root / raw_file
    candidates = [direct] if direct.is_file() else []
    ignored = {".git", "node_modules", "cache", "build", "coverage"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in ignored]
        if basename in filenames:
            path = Path(dirpath) / basename
            if path not in candidates:
                candidates.append(path)

    def rank(path):
        parts = {part.lower() for part in path.parts}
        generated = len(parts & {"artifacts", "out"})
        dependency = len(parts & {"lib", "vendor"})
        exact_suffix = 0 if str(path).endswith(raw_file) else 1
        return (generated, dependency, exact_suffix, len(path.parts), str(path))

    return sorted(candidates, key=rank)


def _extract_source_excerpt(path, finding):
    """Extract the reported function, falling back to a line-centred source window."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = text.splitlines()
    if not lines:
        return ""

    fn = str(finding.get("function") or "").strip()
    line_no = int(finding.get("line") or 0)
    target = max(0, min(len(lines) - 1, line_no - 1)) if line_no else 0
    if fn in {"constructor", "fallback", "receive"}:
        pattern = re.compile(rf"\b{re.escape(fn)}\s*\(")
    elif fn:
        pattern = re.compile(rf"\bfunction\s+{re.escape(fn)}\b")
    else:
        pattern = None

    matches = [i for i, row in enumerate(lines) if pattern and pattern.search(row)]
    if matches:
        preceding = [i for i in matches if i <= target]
        declaration = max(preceding, key=lambda i: i) if preceding else min(matches, key=lambda i: abs(i - target))
        # Include modifiers/comments immediately above the declaration.
        start = max(0, declaration - 2)
        depth = 0
        seen_open = False
        end = min(len(lines), start + 120)
        for i in range(declaration, min(len(lines), declaration + 160)):
            depth += lines[i].count("{") - lines[i].count("}")
            seen_open = seen_open or "{" in lines[i]
            if seen_open and depth <= 0:
                end = i + 1
                break
    else:
        start = max(0, target - 12)
        end = min(len(lines), target + 28)

    numbered = [f"{i + 1}: {lines[i]}" for i in range(start, end)]
    return "\n".join(numbered)[:5000]


def _load_sources_from_files(project, findings):
    """Build the same lookup as `_load_sources` directly from reported files/lines."""
    source_map = {}
    for finding in findings:
        candidates = _source_candidates(project, finding)
        if not candidates:
            continue
        excerpt = _extract_source_excerpt(candidates[0], finding)
        if not excerpt:
            continue
        fn = finding.get("function", "?")
        file_name = str(finding.get("file") or finding.get("contract") or "")
        contract = str(finding.get("contract") or "")
        for key in {
            (file_name.lower(), fn),
            (Path(file_name).name.lower(), fn),
            (contract.lower(), fn),
        }:
            source_map.setdefault(key, excerpt)
    return source_map


def _load_sources(project, findings=None):
    """(file_basename_lower, function_name) -> Solidity source text, for grounding the composition
    prompt in real code (cuts hallucination). Loads via ProjectLoader (DEURO/EUSD/...) or the
    direct-load recipes (BAI/GYEN/DAI+ in scan_direct, BOB in scan_bob). Returns {} on failure."""
    findings = findings or []
    if SOURCE_LOADER == "filesystem":
        return _load_sources_from_files(project, findings)

    from stableguard.stablecoin_specific.detectors import fn_file, fn_text, own_functions
    contracts = None
    original_cwd = Path.cwd()
    try:
        from scan_direct import PROJECTS as DIRECT
        if project in DIRECT:
            from crytic_compile import CryticCompile
            from slither import Slither
            cwd, target, ver, remaps = DIRECT[project]
            os.chdir(cwd)
            contracts = Slither(CryticCompile(target, solc_remaps=remaps, solc_solcs_select=ver)).contracts
    except Exception:
        contracts = None
    finally:
        os.chdir(original_cwd)
    if contracts is None:
        try:
            from stableguard.core.project_loader import ProjectLoader
            ldr = ProjectLoader(str(Path("dataset") / project))
            try:
                contracts = ldr.load().contracts
            except Exception:
                contracts = ldr.load_with_fallback().contracts
        except Exception:
            contracts = None
    if contracts is None:
        return _load_sources_from_files(project, findings) if SOURCE_LOADER == "auto" else {}
    m = {}
    for c in contracts:
        for f in own_functions(c):
            k = (fn_file(f).lower(), f.name)
            if k not in m and fn_text(f):
                m[k] = fn_text(f)
    if not m and SOURCE_LOADER == "auto":
        return _load_sources_from_files(project, findings)
    return m

SYS = (
    "You are a senior smart-contract security auditor performing CROSS-DEFECT COMPOSITION analysis "
    "on a stablecoin contract. You are given several INDIVIDUALLY-confirmed defects on the SAME "
    "contract. Decide whether two or more of them COMPOSE into a multi-step attack path that is "
    "materially MORE severe or more exploitable than any single defect alone.\n\n"
    "A genuine composition = the OUTPUT or STATE-EFFECT of one defect ENABLES, UNLOCKS, or AMPLIFIES "
    "another. Examples: a stale self-referential price makes an under-priced liquidation profitable; "
    "an authorization-gap mint + a liquidation-evasion lets forged unbacked debt persist; a "
    "refresh-revert DoS freezes a stale price so a degenerate-price fire-sale cannot be corrected.\n\n"
    "Be STRICT and SKEPTICAL:\n"
    "- Every path must chain at least TWO DISTINCT defect sub-types (for example S01 + S15); "
    "multiple instances of only one sub-type are not cross-defect composition.\n"
    "- Report a path ONLY if the defects chain CAUSALLY — each step must name which defect it uses "
    "and the concrete state/value it carries to the next step.\n"
    "- REJECT mere co-location ('both live in this contract'), generic restatement of the individual "
    "defects, or a 'path' that is really just one defect.\n"
    "- Prefer FEWER, well-justified paths over many speculative ones. If nothing genuinely composes, "
    "set composes=false and explain why.\n"
    "Output STRICT JSON only."
)

USER_TMPL = """## Contract: {contract}  (project {project})
{ndefects} individually-confirmed defects co-occur here.

### Defect definitions (sub-types present)
{defs}

### The confirmed defects on this contract
{defects}

---
Identify any CAUSAL composition into a multi-step attack path. STRICT JSON only:
{{
  "composes": true | false,
  "attack_paths": [
    {{
      "name": "short name",
      "chained_defects": ["Sxx", "Syy", ...],
      "steps": ["1. uses Sxx: ...", "2. uses Syy: ... (carries <state> from step 1)", ...],
      "preconditions": "attacker capabilities / market conditions needed",
      "net_effect": "the unbacked-mint / peg-break / drain outcome",
      "severity": "critical|high|medium",
      "confidence": 0.0-1.0,
      "why_worse_than_parts": "why the chain exceeds the worst single defect"
    }}
  ],
  "why_no_composition": "if composes=false, why the defects do NOT chain"
}}"""


def _defect_block(g, srcmap, contract):
    """One defect rendered for the prompt: type + mechanism + (grounded) real function source."""
    mech = str((g.get("reasoning") or {}).get("mechanism", "") or g.get("reason", ""))[:300]
    fn = g.get("function", "?")
    line = f"- [{g['sub']}] {fn}(): {mech}"
    if srcmap:
        src = srcmap.get(((contract or "").lower(), fn))
        if src:
            line += f"\n  ```solidity\n  {src[:PER_FN]}\n  ```"
    return line


SYS_PROJ = (
    "You are a senior smart-contract security auditor performing PROJECT-LEVEL, CROSS-CONTRACT "
    "composition analysis on a stablecoin protocol. You are given the confirmed defects across "
    "MULTIPLE contracts of one protocol. Find attack paths whose steps span DIFFERENT contracts — "
    "where a defect in contract A produces a state/value that ENABLES or AMPLIFIES a defect in "
    "contract B (e.g. a mis-valuation in an Oracle/Collateral contract feeds an under-priced "
    "liquidation in a Position contract that then mints unbacked units via the token contract).\n\n"
    "Be STRICT: every reported path MUST cross at least TWO contracts, and each step must name the "
    "contract+defect it uses and the concrete value/state carried across the contract boundary. "
    "Every path must also chain at least TWO DISTINCT defect sub-types; repeated instances of one "
    "sub-type across contracts are not cross-defect composition. "
    "REJECT single-contract chains (those are handled separately), co-location, and restatement. "
    "Prefer a few high-confidence cross-contract paths. Output STRICT JSON only."
)
USER_PROJ_TMPL = """## Protocol: {project} — cross-contract composition
Confirmed defects, grouped by contract:

{by_contract}

### Sub-type definitions
{defs}

---
Find CROSS-CONTRACT attack paths (each must span >=2 contracts). STRICT JSON only:
{{
  "composes": true | false,
  "attack_paths": [
    {{
      "name": "short name",
      "contracts_involved": ["A.sol", "B.sol", ...],
      "chained_defects": ["A.sol:Sxx", "B.sol:Syy", ...],
      "steps": ["1. A.sol Sxx: ... (produces <value>)", "2. B.sol Syy: ... (consumes <value> from step 1)"],
      "preconditions": "...",
      "net_effect": "...",
      "severity": "critical|high|medium",
      "confidence": 0.0-1.0
    }}
  ],
  "why_no_composition": "if composes=false"
}}"""


def analyze_project(llm, kb, project, findings, srcmap=None, per_contract_cap=6):
    """Project-level CROSS-CONTRACT composition: reason over defects spanning multiple files."""
    bycontract = defaultdict(list)
    for v in findings:
        bycontract[v.get("file") or v.get("contract")].append(v)
    if len(bycontract) < 2 or len({item.get("sub") for item in findings}) < MIN_SUBS:
        return None
    lines, subs = [], set()
    for contract, group in sorted(bycontract.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"**{contract}**")
        for g in group[:per_contract_cap]:
            subs.add(g["sub"])
            block = _defect_block(g, srcmap, contract)
            if "```solidity" in block:
                head, source = block.split("```solidity", 1)
                source = source[:PROJECT_PER_FN]
                block = head + "```solidity" + source
            lines.append("  " + block.replace("\n", "\n  "))
    defs = "\n".join(
        f"- {s} ({kb.get(s, {}).get('macro','')}) {kb.get(s, {}).get('name','')}: "
        f"{(kb.get(s, {}).get('definition','') or '').strip()[:180]}" for s in sorted(subs))
    by_contract_text = "\n".join(lines)[:PROJECT_SOURCE_CAP]
    usr = USER_PROJ_TMPL.format(project=project, by_contract=by_contract_text, defs=defs)
    r = llm.complete([{"role": "system", "content": SYS_PROJ}, {"role": "user", "content": usr}],
                     max_tokens=PROJECT_MAX_TOKENS,
                     response_format={"type": "json_object"} if JSON_MODE else None)
    verdict = extract_json(r.content) or {"composes": None, "raw": r.content[:400]}
    verdict = _filter_same_subtype_paths(verdict)
    verdict["_usage"] = r.usage.to_dict()
    return verdict


def analyze(llm, kb, project, contract, group, srcmap=None):
    subs = sorted({g["sub"] for g in group})
    defs = "\n".join(
        f"- {s} ({kb.get(s, {}).get('macro','')}) {kb.get(s, {}).get('name','')}: "
        f"{(kb.get(s, {}).get('definition','') or '').strip()[:240]}" for s in subs)
    defects = "\n".join(_defect_block(g, srcmap, contract) for g in group)
    usr = USER_TMPL.format(contract=contract, project=project, ndefects=len(group),
                           defs=defs, defects=defects)
    r = llm.complete([{"role": "system", "content": SYS}, {"role": "user", "content": usr}],
                     max_tokens=CONTRACT_MAX_TOKENS,
                     response_format={"type": "json_object"} if JSON_MODE else None)
    verdict = extract_json(r.content) or {"composes": None, "raw": r.content[:400]}
    verdict = _filter_same_subtype_paths(verdict)
    verdict["_usage"] = r.usage.to_dict()
    return verdict


def _filter_same_subtype_paths(verdict):
    """Enforce the method's cross-defect requirement on model-generated paths."""
    if not verdict.get("composes"):
        return verdict
    paths = verdict.get("attack_paths") or []
    kept = []
    removed = []
    for path in paths:
        subtypes = {
            match.group(0)
            for raw in path.get("chained_defects") or []
            if (match := re.search(r"\bS\d{2}\b", str(raw)))
        }
        if len(subtypes) >= MIN_SUBS:
            kept.append(path)
        else:
            removed.append(path)
    if removed:
        verdict["_filtered_same_subtype_paths"] = len(removed)
        verdict["attack_paths"] = kept
        if not kept:
            verdict["composes"] = False
            verdict["why_no_composition"] = (
                "All generated paths repeated a single defect sub-type and were removed by "
                "the cross-defect constraint."
            )
    return verdict


def run(in_dir=IN, out_dir=OUT, projects=None, ground=GROUND):
    """Programmatic entry (used by the scan pipeline hook). Analyzes every per-project scan JSON in
    `in_dir`, writes per-project composition results to `out_dir`. Returns a summary dict."""
    in_dir, out_dir = Path(in_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kb = load_kb()
    llm = LLMClient()
    summary = {
        "projects": 0,
        "grounded_projects": 0,
        "calls": 0,
        "contracts_with_paths": 0,
        "total_paths": 0,
        "model": llm.model,
        "source_loader": SOURCE_LOADER,
        "contract_max_tokens": CONTRACT_MAX_TOKENS,
        "project_max_tokens": PROJECT_MAX_TOKENS,
        "json_mode": JSON_MODE,
    }
    for f in sorted(in_dir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text())
        project = d.get("project") or f.stem
        if projects and project not in projects:
            continue
        summary["projects"] += 1
        bycontract = defaultdict(list)
        for v in d.get("findings", []) or []:
            bycontract[v.get("file") or v.get("contract")].append(v)
        findings = d.get("findings", []) or []
        srcmap = _load_sources(project, findings) if ground else {}
        if ground:
            print(f"[{project}] source grounding: {len(srcmap)} functions loaded", file=sys.stderr)
        if srcmap:
            summary["grounded_projects"] += 1
        out = {
            "project": project,
            "grounded": bool(srcmap),
            "source_loader": SOURCE_LOADER,
            "model": llm.model,
            "contracts": [],
        }
        for contract, group in bycontract.items():
            if len({g["sub"] for g in group}) < MIN_SUBS:
                continue
            verdict = analyze(llm, kb, project, contract, group, srcmap)
            summary["calls"] += 1
            paths = verdict.get("attack_paths") or []
            out["contracts"].append({"contract": contract, "n_defects": len(group),
                                     "subs": sorted({g["sub"] for g in group}),
                                     "verdict": verdict})
            np = len(paths) if verdict.get("composes") else 0
            if np:
                summary["contracts_with_paths"] += 1
                summary["total_paths"] += np
            print(f"  {project}/{contract}: {len(group)} defects {sorted({g['sub'] for g in group})} "
                  f"-> composes={verdict.get('composes')} paths={np}", file=sys.stderr)
        # step 3: project-level CROSS-CONTRACT composition (attacks that span multiple files)
        if os.getenv("CROSS_FILE", "1") != "0":
            pv = analyze_project(llm, kb, project, d.get("findings", []) or [], srcmap)
            if pv is not None:
                summary["calls"] += 1
                out["project_level"] = pv
                pp = len(pv.get("attack_paths") or []) if pv.get("composes") else 0
                summary["total_paths"] += pp
                print(f"  {project} [CROSS-CONTRACT]: composes={pv.get('composes')} paths={pp}",
                      file=sys.stderr)
        (out_dir / f"{project}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    summary["usage"] = llm.cumulative_usage.to_dict()
    (out_dir / "_run_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )
    print(f"cross-defect analysis -> {out_dir}/ "
          f"({summary['total_paths']} paths in {summary['contracts_with_paths']} contracts)", file=sys.stderr)
    return summary


def main():
    run(IN, OUT, projects=(sys.argv[1:] or None), ground=GROUND)


if __name__ == "__main__":
    main()
