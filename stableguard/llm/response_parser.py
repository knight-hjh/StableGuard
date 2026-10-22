"""
Parse LLM responses into structured Python objects.

Handles common issues:
- LLM wraps JSON in ```json ... ``` fences
- Trailing/leading prose around JSON
- Minor JSON formatting issues
"""
import json
import re
from typing import Any, Dict, Optional
from loguru import logger


JSON_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE
)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract a JSON object from LLM-generated text.

    Tries (in order):
    1. Parse the whole text as JSON
    2. Find content inside ```json ... ``` fences
    3. Find the first {...} block via brace matching
    """
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: fenced block
    for match in JSON_FENCE_PATTERN.finditer(text):
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Strategy 3: greedy {...} block by brace matching
    candidate = _extract_outermost_object(text)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            logger.warning(f"Brace-matched JSON failed to parse: {e}")

    return None


def _extract_outermost_object(text: str) -> Optional[str]:
    """Find the outermost balanced { ... } in text."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_detection_response(text: str) -> Dict[str, Any]:
    """
    Parse a detection-task response. Returns a dict with normalized keys.

    Expected schema (from prompt):
    {
      "defect_present": true | false | "uncertain",
      "confidence": 0.0 - 1.0,
      "reasoning": {...},  # multi-step CoT
      "exploit_path": "..." or null,
      "severity": "critical" | "high" | "medium" | "low" | "info",
      "affected_locations": [{"file": ..., "line": ...}],
      "supporting_facts": [fact_id, ...]
    }
    """
    parsed = extract_json(text)
    if parsed is None:
        return {
            "_parse_error": "Could not extract JSON from response",
            "_raw_text": text,
        }

    # Normalize defect_present (LLM might return strings)
    dp = parsed.get("defect_present")
    if isinstance(dp, str):
        dp_lower = dp.strip().lower()
        if dp_lower in ("true", "yes"):
            parsed["defect_present"] = True
        elif dp_lower in ("false", "no"):
            parsed["defect_present"] = False
        else:
            parsed["defect_present"] = "uncertain"

    # Normalize actual_defect_type (Fix 3, v1.4)
    # LLM may set this when its analysis matches a different defect
    # family than the router's nominal task type.
    _VALID_DEFECT_TYPES = {
        "HardcodedStablecoinPeg",
        "OracleFailureHandlingGap",
        "InvalidCollateralToStablecoinConversion",
        "ParameterConflation",
        "RedemptionOrderVulnerability",
        "ZombieTrove",
        "PartialRedemptionLoopBreak",
        "IntegerRounding",
        "AssumeNoLowCostExploits",
        "TCRCalculationFlaw",
    }
    adt = parsed.get("actual_defect_type")
    if isinstance(adt, str):
        adt_clean = adt.strip()
        if adt_clean in _VALID_DEFECT_TYPES:
            parsed["actual_defect_type"] = adt_clean
        elif adt_clean == "" or adt_clean.lower() in ("null", "none"):
            parsed["actual_defect_type"] = None
        else:
            # Non-canonical name — preserve as-is for evaluator to inspect
            parsed["actual_defect_type"] = adt_clean
    else:
        parsed["actual_defect_type"] = None

    # Ensure confidence is float
    if "confidence" in parsed:
        try:
            parsed["confidence"] = float(parsed["confidence"])
        except (ValueError, TypeError):
            parsed["confidence"] = 0.0

    # Ensure lists are lists
    for key in ("affected_locations", "supporting_facts"):
        if key in parsed and not isinstance(parsed[key], list):
            parsed[key] = []

    return parsed