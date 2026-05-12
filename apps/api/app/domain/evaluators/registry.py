from __future__ import annotations

from typing import Any, Callable

from app.domain.evaluators import (
    cosine_similarity,
    exact_match,
    json_schema_valid,
    keyword_presence,
    length_bounds,
    llm_judge,
    regex_match,
)
from app.domain.evaluators.base import EvaluatorResult

RunFn = Callable[[dict, dict[str, Any]], EvaluatorResult]

REGISTRY: dict[str, RunFn] = {
    "regex_match": regex_match.run,
    "keyword_presence": keyword_presence.run,
    "length_bounds": length_bounds.run,
    "json_schema_valid": json_schema_valid.run,
    "exact_match": exact_match.run,
    "cosine_similarity": cosine_similarity.run,
    "llm_judge": llm_judge.run,
}
