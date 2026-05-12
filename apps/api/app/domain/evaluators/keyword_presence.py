from __future__ import annotations

import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_path: str = config.get("target", "")
    keywords: list[str] = config.get("keywords", [])
    require: str = config.get("require", "any")  # any | all | none

    text = resolve_dotpath(target_path, context).lower()
    matched = [kw for kw in keywords if kw.lower() in text]
    total = len(keywords)

    if require == "all":
        score = len(matched) / max(total, 1)
        passed = len(matched) == total
    elif require == "none":
        score = 1.0 if not matched else 0.0
        passed = not matched
    else:  # any
        score = 1.0 if matched else 0.0
        passed = bool(matched)

    latency_ms = int((time.monotonic() - t0) * 1000)
    return EvaluatorResult(
        score=score,
        passed=passed,
        reasoning=f"Matched {len(matched)}/{total} keywords (require={require})",
        raw_output={"matched": matched, "require": require},
        latency_ms=latency_ms,
    )
