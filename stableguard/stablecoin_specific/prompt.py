"""Prompt builder for the C1-C5 hybrid stage (fix-AGNOSTIC pattern recognition)."""
from __future__ import annotations
import os
import yaml
from functools import lru_cache

_KB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "config", "knowledge_base", "c1c5_kb.yaml")


@lru_cache(maxsize=1)
def load_kb() -> dict:
    with open(_KB_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


SYSTEM_PROMPT = (
    "You are a senior stablecoin smart-contract auditor. You are given a candidate code "
    "location flagged by a high-recall static detector, and the definition of ONE specific "
    "stablecoin defect sub-type. Your job: decide whether this code location genuinely "
    "exhibits the defect PATTERN / MECHANISM of that sub-type.\n\n"
    "IMPORTANT — be FIX-AGNOSTIC and PRECISE. `defect_present=true` means 'this code location "
    "IS a site of this defect TYPE / SUBSYSTEM', NOT 'an exploitable bug exists right now':\n"
    "- The sub-type names a SUBSYSTEM / code path (e.g. S03 = a liquidation/forced-sale's bad-debt "
    "settlement path; S16 = collateral payout during challenge settlement; S11 = a backing/revenue "
    "accounting read). If THIS function implements that subsystem, set defect_present=true — EVEN IF "
    "it currently handles it correctly, has a guard (coverLoss, a check, a cap), or looks like the "
    "patched version. We are mapping defect-type locations; note any mitigation in `mitigation`.\n"
    "- Reject (defect_present=false) ONLY when the code is a DIFFERENT subsystem/defect type, is "
    "vendored/library/test boilerplate, or merely shares a keyword without implementing the "
    "sub-type's subsystem at all.\n"
    "- Output STRICT JSON only, no prose around it."
)

USER_TMPL = """## Target defect sub-type: {sub} ({macro}) — {name}

**Definition.** {definition}

**Pattern signals (suggest THIS defect):**
{pos}

**NOT this defect (reject these):**
{neg}

**Stablecoin impact.** {impact}

---
## Candidate location (flagged by static detector)
- contract: `{contract}`  |  file: `{file}`  |  function: `{function}` (line {line})
- detector reason: {reason}

## Function source
```solidity
{code}
```

---
Reason step by step, then output STRICT JSON ONLY:
```json
{{
  "defect_present": true | false | "uncertain",
  "matches_subtype": "{sub}" or null,
  "confidence": 0.0-1.0,
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "reasoning": {{
    "pattern_match": "does the code exhibit the sub-type's mechanism? which signals?",
    "mechanism": "how the backing/peg invariant is (or could be) broken here",
    "mitigation": "any guard that mitigates it (still classify the type), or null"
  }}
}}
```"""


NO_FACTS_TMPL = """## Target defect sub-type: {sub} ({macro}) — {name}

**Definition.** {definition}

**Stablecoin impact.** {impact}

---
## Candidate location
- contract: `{contract}`  |  file: `{file}`  |  function: `{function}` (line {line})

## Function source
```solidity
{code}
```

---
Decide whether this code location genuinely exhibits the target stablecoin defect sub-type.
Do not rely on detector-provided facts, pattern signals, or routing explanations; use only
the source code and the sub-type definition above.

Output STRICT JSON ONLY:
```json
{{
  "defect_present": true | false | "uncertain",
  "matches_subtype": "{sub}" or null,
  "confidence": 0.0-1.0,
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "reasoning": {{
    "pattern_match": "what in the code matches or does not match the target definition",
    "mechanism": "stablecoin backing/peg mechanism, or null",
    "mitigation": "guard or mitigating condition, or null"
  }}
}}
```"""

GENERIC_TARGET_TMPL = """You are given a static candidate location and the full StableGuard C1-C5/S01-S19 taxonomy.
Unlike the full StableGuard grouped detector, do not use subtype-specific pattern signals.
Use a single generic stablecoin-defect detector and decide whether the candidate is a real
stablecoin-specific defect of the target subtype.

## Target subtype
{sub} ({macro}) — {name}: {definition}

## Candidate
- contract: `{contract}`  |  file: `{file}`  |  function: `{function}` (line {line})
- detector reason: {reason}

## Function source
```solidity
{code}
```

Output STRICT JSON ONLY:
```json
{{
  "defect_present": true | false | "uncertain",
  "matches_subtype": "{sub}" or null,
  "confidence": 0.0-1.0,
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "reasoning": {{
    "pattern_match": "why the generic detector accepts or rejects this target subtype",
    "mechanism": "stablecoin-specific mechanism, or null",
    "mitigation": "guard or mitigating condition, or null"
  }}
}}
```"""

NO_ROUTING_TMPL = """You are given a static candidate location, but the subtype router has been removed.
Inspect the code and classify it against the full StableGuard stablecoin-defect taxonomy.

## C1-C5/S01-S19 taxonomy
{taxonomy}

## Candidate location
- contract: `{contract}`  |  file: `{file}`  |  function: `{function}` (line {line})
- static detector hint: {reason}

## Function source
```solidity
{code}
```

Output STRICT JSON ONLY:
```json
{{
  "defect_present": true | false | "uncertain",
  "matches_subtype": "S01" | "S02" | ... | "S19" | null,
  "confidence": 0.0-1.0,
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "reasoning": {{
    "pattern_match": "which subtype, if any, this code matches",
    "mechanism": "stablecoin-specific mechanism, or null",
    "mitigation": "guard or mitigating condition, or null"
  }}
}}
```"""


def taxonomy_text() -> str:
    kb = load_kb()
    lines = []
    for sub in sorted(kb):
        e = kb.get(sub, {})
        lines.append(f"- {sub} ({e.get('macro', '')}) {e.get('name', '')}: {e.get('definition', '').strip()}")
    return "\n".join(lines)


def build_prompt(candidate, code: str, mode: str = "full") -> str:
    kb = load_kb()
    e = kb.get(candidate.sub, {})
    if mode == "no_facts":
        return NO_FACTS_TMPL.format(
            sub=candidate.sub, macro=e.get("macro", ""), name=e.get("name", ""),
            definition=e.get("definition", "").strip(), impact=e.get("stablecoin_impact", ""),
            contract=candidate.contract, file=candidate.file, function=candidate.function,
            line=candidate.line, code=(code or "// source unavailable")[:6000],
        )
    if mode == "no_grouped_agent":
        return GENERIC_TARGET_TMPL.format(
            sub=candidate.sub, macro=e.get("macro", ""), name=e.get("name", ""),
            definition=e.get("definition", "").strip(), contract=candidate.contract,
            file=candidate.file, function=candidate.function, line=candidate.line,
            reason=candidate.reason, code=(code or "// source unavailable")[:6000],
        )
    if mode == "no_routing":
        return NO_ROUTING_TMPL.format(
            taxonomy=taxonomy_text(), contract=candidate.contract, file=candidate.file,
            function=candidate.function, line=candidate.line, reason=candidate.reason,
            code=(code or "// source unavailable")[:6000],
        )
    pos = "\n".join(f"- {s}" for s in e.get("pattern_signals", [])) or "- (none)"
    neg = "\n".join(f"- {s}" for s in e.get("not_this_defect", [])) or "- (none)"
    return USER_TMPL.format(
        sub=candidate.sub, macro=e.get("macro", ""), name=e.get("name", ""),
        definition=e.get("definition", "").strip(), pos=pos, neg=neg,
        impact=e.get("stablecoin_impact", ""),
        contract=candidate.contract, file=candidate.file, function=candidate.function,
        line=candidate.line, reason=candidate.reason,
        code=(code or "// source unavailable")[:6000],
    )
