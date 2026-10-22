#!/usr/bin/env python3
"""C1-C5 hybrid scan: static detectors -> LLM pattern-recognition verdict.

For each project: load -> run_detectors -> for each candidate render the C1-C5 prompt
(KB + function source) -> LLMClient verdict -> save findings tagged with {sub, file, ...}.
Output feeds scripts/eval_stablecoin_specific.py for per-S/per-C precision.

Usage:
  PROJECT_LIST=dataset/project-list.txt SCAN_OUT=logs/c1c5_scan python3 scripts/scan_c1c5.py
  python3 scripts/scan_c1c5.py EUSD DEURO              # explicit projects
Env: SCAN_OUT (default logs/c1c5_scan), JOBS (default 4), SUBS (comma list to limit sub-types).
"""
import json, os, re, signal, sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from loguru import logger
from dotenv import load_dotenv

load_dotenv()
logger.remove(); logger.add(sys.stderr, level="WARNING")
sys.path.insert(0, str(Path(__file__).parent.parent))

from stableguard.core.project_loader import ProjectLoader
from stableguard.stablecoin_specific import run_detectors
from stableguard.stablecoin_specific.prompt import build_prompt, SYSTEM_PROMPT
from stableguard.llm.client import LLMClient
from stableguard.llm.response_parser import parse_detection_response
from static_screening.lib.stablecoin_specific import SUBDEFECTS

DATASET = Path("dataset/projects")
OUT = Path(os.getenv("SCAN_OUT", "logs/c1c5_scan")); OUT.mkdir(parents=True, exist_ok=True)
PROBE = {d["project"]: d for d in json.loads(Path("logs/build_probe.json").read_text())} \
    if Path("logs/build_probe.json").exists() else {}
SUBS = set((os.getenv("SUBS", "") or "").split(",")) - {""} or None
PARSE_TIMEOUT = int(os.getenv("SCAN_PARSE_TIMEOUT", "420"))
NO_INLINE = os.getenv("NO_INLINE") == "1"   # ablation: disable callee-inlining (RQ2 controlled)
ABLATION_MODE = os.getenv("ABLATION_MODE", "full")


class _TO(Exception): pass
def _h(s, f): raise _TO()
def safe(n): return re.sub(r"[^A-Za-z0-9_.-]", "_", n).strip("_")


def _fn_text_map(contracts):
    """(file_basename_lower, function_name) -> source text, for prompt code snippets."""
    from stableguard.stablecoin_specific.detectors import fn_file, fn_text, own_functions
    m = {}
    for c in contracts:
        for f in own_functions(c):
            key = (fn_file(f).lower(), f.name)
            if key not in m:
                t = fn_text(f)
                if t:
                    m[key] = t
    return m


def _impl_map(contracts):
    """function name -> implemented body text (concrete only). For inlining callees so the LLM
    can reason across calls (a defect's mint/transfer may live several calls deep)."""
    from stableguard.stablecoin_specific.detectors import fn_text, own_functions
    m = {}
    for c in contracts:
        for f in own_functions(c):
            if getattr(f, "is_implemented", True) and f.name not in m:
                t = fn_text(f)
                if t:
                    m[f.name] = t
    return m


# tokens that make a callee body worth inlining (value movement / accounting / pricing) — these
# are where cross-function defects actually manifest (e.g. _finishChallenge -> coverLoss ->
# _withdrawFromReserve -> _mint(shortfall)). A callee is kept only if it (or one of its own
# callees) carries such a token, so we don't bloat the prompt with getters.
_CALLEE_SIGNAL = re.compile(
    r"\b_?mint\s*\(|\b_?burn\s*\(|coverLoss|withdrawFromReserve|reserveLeft|amount\s*-\s*reserve|"
    r"distributeProfits|collectProfits|exchangeRate|latestRoundData|\.price\s*\(|"
    r"redeem|liquidat|forceSale", re.I)
# Skip control-keywords AND standard ERC20/ownership plumbing — their bodies are boilerplate that
# never holds the defect (inlining them just burns the prompt budget before the real callee chain).
_CALLEE_SKIP = {"require", "revert", "assert", "if", "for", "while", "return", "emit",
                "address", "uint256", "uint", "int", "bool", "msg", "abi", "keccak256",
                "transfer", "transferFrom", "approve", "allowance", "balanceOf", "totalSupply",
                "_transfer", "_approve", "_spendAllowance", "_msgSender", "owner", "decimals",
                "_beforeTokenTransfer", "_afterTokenTransfer"}


_STRONG_SIGNAL = re.compile(r"\b_?mint\s*\(|reserveLeft|coverLoss|amount\s*-\s*reserve|exchangeRate", re.I)


def _augment_code(code, impl, depth=3, budget=5800):
    """code (candidate fn source) + bodies of the signal-bearing functions it transitively calls,
    so the judge sees a mint/transfer that lives a few calls away. Strongest-signal callees (the
    ones that actually mint / draw reserve) are inlined first; capped to `budget` chars."""
    if not code:
        return code
    kept, seen = {}, set()

    def walk(text, d):
        if d == 0:
            return False
        deep_signal = False
        for n in dict.fromkeys(re.findall(r"\.?([A-Za-z_]\w*)\s*\(", text)):
            if n in _CALLEE_SKIP or n not in impl:
                continue
            if n in seen:
                deep_signal = deep_signal or n in kept
                continue
            seen.add(n)
            body = impl[n]
            child = walk(body, d - 1)
            if _CALLEE_SIGNAL.search(body) or child:
                kept[n] = body
                deep_signal = True
        return deep_signal

    walk(code, depth)
    if not kept:
        return code
    # strongest-signal callees first so a deep _mint/reserve draw survives the budget cap
    ordered = sorted(kept.items(), key=lambda kv: 0 if _STRONG_SIGNAL.search(kv[1]) else 1)
    out = code + "\n\n// ---- called functions (resolved implementations, for cross-call context) ----\n"
    for n, body in ordered:
        chunk = f"\n// {n}()\n{body}\n"
        if len(out) + len(chunk) > budget:
            continue
        out += chunk
    return out


def add_usage(out, response):
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


def scan_one(name):
    out = {"project": name, "status": "unknown", "n_candidates": 0,
           "findings": [], "all_verdicts": [], "error": None}
    proj = DATASET / name
    ver = (PROBE.get(name) or {}).get("pragmas")
    ver = ver[0][0] if ver else None
    if ver:
        os.environ["SOLC_VERSION"] = ver
    signal.signal(signal.SIGALRM, _h); signal.alarm(PARSE_TIMEOUT)
    try:
        loader = ProjectLoader(str(proj), solc_version=ver)
        try:
            sl = loader.load()
        except Exception:
            sl = loader.load_with_fallback()
        contracts = sl.contracts
        cands = run_detectors(contracts, only=SUBS)
        signal.alarm(0)
        out["n_candidates"] = len(cands)
        if not cands:
            out["status"] = "ok_no_candidates"; return out
        textmap = _fn_text_map(contracts)
        impl = _impl_map(contracts)
        llm = LLMClient()
        out["model"] = llm.model
        out["ablation_mode"] = ABLATION_MODE
        for c in cands:
            code = textmap.get((c.file.lower(), c.function), "")
            if not NO_INLINE:
                code = _augment_code(code, impl)  # inline signal-bearing callees (cross-call context)
            prompt = build_prompt(c, code, mode=ABLATION_MODE)
            try:
                resp = llm.complete([{"role": "system", "content": SYSTEM_PROMPT},
                                     {"role": "user", "content": prompt}], max_tokens=900)
                add_usage(out, resp)
                parsed = parse_detection_response(resp.content)
            except Exception as e:
                out["all_verdicts"].append({**c.to_dict(), "defect_present": "error",
                                            "error": str(e)[:120]})
                continue
            matched_sub = parsed.get("matches_subtype")
            if isinstance(matched_sub, str):
                matched_sub = matched_sub.strip().upper()
            if ABLATION_MODE == "no_routing" and matched_sub in SUBDEFECTS:
                cdict = {**c.to_dict(), "routed_sub": c.sub, "sub": matched_sub}
            else:
                cdict = c.to_dict()
            v = {**cdict,
                 "defect_present": parsed.get("defect_present"),
                 "confidence": parsed.get("confidence"),
                 "severity": parsed.get("severity")}
            out["all_verdicts"].append(v)
            if parsed.get("defect_present") is True:
                out["findings"].append({**v, "reasoning": parsed.get("reasoning")})
        out["status"] = "ok"
    except _TO:
        out["status"] = "timeout"
    except Exception as e:
        out["status"] = "error"; out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        signal.alarm(0)
    return out


def worker(name):
    cp = OUT / f"{safe(name)}.json"
    if cp.exists():
        return {"project": name, "status": "skip"}
    try:
        res = scan_one(name)
    except Exception as e:
        res = {"project": name, "status": "crash", "error": str(e)[:200]}
    cp.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return {"project": name, "status": res.get("status"),
            "cands": res.get("n_candidates", 0), "findings": len(res.get("findings", []))}


def main():
    if len(sys.argv) > 1:
        names = sys.argv[1:]
    else:
        lf = os.getenv("PROJECT_LIST", "dataset/project-list.txt")
        names = [l.strip() for l in Path(lf).read_text().splitlines() if l.strip()]
    names = [n for n in names if (DATASET / n).is_dir()]
    logger.warning(f"C1-C5 hybrid scan: {len(names)} projects -> {OUT}/ (subs={SUBS or 'ALL'})")
    jobs = int(os.getenv("JOBS", "4"))
    done = 0
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(worker, n): n for n in names}
        for fu in as_completed(futs):
            done += 1
            s = fu.result()
            logger.warning(f"[{done}/{len(names)}] {s['project']} -> {s.get('status')} "
                           f"cands={s.get('cands','?')} findings={s.get('findings','?')}")
    logger.warning("C1-C5 hybrid scan complete.")
    # Pipeline hook: optionally chain the cross-defect COMPOSITION stage over the just-written
    # findings (RUN_CROSS=1). Static rules judge defects in isolation; this stage reasons about how
    # the co-occurring confirmed defects on a contract compose into multi-step attack paths.
    if os.getenv("RUN_CROSS") == "1":
        try:
            from cross_defect_c1c5 import run as run_cross
            cross_out = os.getenv("CROSS_OUT", str(OUT) + "_cross")
            logger.warning(f"cross-defect composition stage -> {cross_out}/")
            s = run_cross(in_dir=OUT, out_dir=cross_out, projects=(names if len(sys.argv) > 1 else None))
            logger.warning(f"cross-defect stage complete: {s}")
        except Exception as e:
            logger.warning(f"cross-defect stage failed: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
