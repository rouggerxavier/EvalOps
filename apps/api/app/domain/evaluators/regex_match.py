from __future__ import annotations

import re
import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_path: str = config.get("target", "")
    pattern: str = config.get("pattern", "")
    mode: str = config.get("mode", "must_match")  # must_match | must_not_match
    flags_list: list[str] = config.get("flags", [])

    flag_bits = 0
    for f in flags_list:
        flag_bits |= getattr(re, f.upper(), 0)

    text = resolve_dotpath(target_path, context)
    matched = bool(re.search(pattern, text, flag_bits))

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
