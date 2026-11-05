from __future__ import annotations

import re
import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath
from app.domain.rubrics.templating import render_template


def _normalize(text: str, ops: list[str]) -> str:
    if "lowercase" in ops:
        text = text.lower()
    if "strip" in ops:
        text = text.strip()
    if "collapse_spaces" in ops:
        text = re.sub(r"\s+", " ", text)
    return text


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_path: str = config.get("target", "")
    expected_template: str = config.get("expected", "")
    normalize_ops: list[str] = config.get("normalize", [])

    actual = resolve_dotpath(target_path, context)

    # Render expected template using basic dotpath substitution (Jinja2-lite)
    try:
        expected = render_template(expected_template, context)
    except Exception:  # noqa: BLE001
        expected = expected_template

    actual_norm = _normalize(actual, normalize_ops)
    expected_norm = _normalize(expected, normalize_ops)
    passed = actual_norm == expected_norm

    latency_ms = int((time.monotonic() - t0) * 1000)
    return EvaluatorResult(
        score=1.0 if passed else 0.0,
        passed=passed,
        reasoning=f"Actual vs expected: {'match' if passed else 'no match'}",
        raw_output={"actual": actual_norm[:200], "expected": expected_norm[:200]},
        latency_ms=latency_ms,
    )
