from __future__ import annotations

import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_path: str = config.get("target", "")
    # chars | words | tokens
    unit: str = config.get("unit") or ("words" if "min_words" in config or "max_words" in config else "chars")
    min_val: int | None = config.get("min") or config.get("min_chars") or config.get("min_words")
    max_val: int | None = config.get("max") or config.get("max_chars") or config.get("max_words")

    text = resolve_dotpath(target_path, context)

    if unit == "words":
        length = len(text.split())
    else:  # chars or tokens (tokens approximate as chars)
        length = len(text)

    within_bounds = True
    score = 1.0

    if min_val is not None and length < min_val:
        within_bounds = False
        # Linear degradation: at 0 → score=0; at min*(1-0.2) → score=0
        tolerance = min_val * 0.2
        score = max(0.0, length / max(min_val - tolerance, 1))

    if max_val is not None and length > max_val:
        within_bounds = False
        tolerance = max_val * 0.2
        over = length - max_val
        score = max(0.0, 1.0 - over / max(tolerance, 1))

    passed = within_bounds
    latency_ms = int((time.monotonic() - t0) * 1000)
    return EvaluatorResult(
        score=min(1.0, max(0.0, score)),
        passed=passed,
        reasoning=f"Length={length} {unit} (min={min_val}, max={max_val})",
        raw_output={"length": length, "unit": unit},
        latency_ms=latency_ms,
    )
