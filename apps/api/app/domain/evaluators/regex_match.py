from __future__ import annotations

import time
from typing import Any

import regex

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath

# `re` has no timeout: a pattern such as (a+)+$ hangs the worker on a long text that almost matches.
MATCH_TIMEOUT_SECONDS = 1.0


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_path: str = config.get("target", "")
    pattern: str = config.get("pattern", "")
    mode: str = config.get("mode", "must_match")  # must_match | must_not_match
    flags_list: list[str] = config.get("flags", [])

    flag_bits = 0
    for f in flags_list:
        flag_bits |= getattr(regex, f.upper(), 0)

    text = resolve_dotpath(target_path, context)
    try:
        matched = bool(regex.search(pattern, text, flag_bits, timeout=MATCH_TIMEOUT_SECONDS))
    except TimeoutError:
        # Not measured: neither a pass nor a fail of the trace.
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning="regex_timeout",
            raw_output={"error": "regex_timeout", "mode": mode},
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    if mode == "must_match":
        passed = matched
    else:  # must_not_match
        passed = not matched

    score = 1.0 if passed else 0.0
    latency_ms = int((time.monotonic() - t0) * 1000)
    return EvaluatorResult(
        score=score,
        passed=passed,
        reasoning=f"Pattern {'matched' if matched else 'did not match'} (mode={mode})",
        raw_output={"matched": matched, "mode": mode},
        latency_ms=latency_ms,
    )
