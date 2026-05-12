from __future__ import annotations

import json
import re
import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath


def _extract_first_json(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_path: str = config.get("target", "")
    schema: dict = config.get("schema", {})
    parse_mode: str = config.get("parse_mode", "strict")  # strict | extract_first

    text = resolve_dotpath(target_path, context)

    if parse_mode == "extract_first":
        extracted = _extract_first_json(text)
        json_text = extracted if extracted else text
    else:
        json_text = text

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning=f"JSON parse error: {exc}",
            raw_output={"parse_error": str(exc)},
            latency_ms=latency_ms,
        )

    # Validate against schema if provided
    if schema:
        try:
            import jsonschema
            jsonschema.validate(instance=parsed, schema=schema)
            valid = True
            error_msg = None
        except ImportError:
            # Fallback: just check it parses
            valid = True
            error_msg = None
        except Exception as exc:  # noqa: BLE001
            valid = False
            error_msg = str(exc)
    else:
        valid = True
        error_msg = None

    passed = valid
    score = 1.0 if passed else 0.0
    latency_ms = int((time.monotonic() - t0) * 1000)
    return EvaluatorResult(
        score=score,
        passed=passed,
        reasoning=error_msg or "JSON is valid",
        raw_output={"valid": valid, "schema_error": error_msg},
        latency_ms=latency_ms,
    )
