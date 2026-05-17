from __future__ import annotations

import math
import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath
from app.safe_errors import safe_message


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine(a: list[float], b: list[float]) -> float:
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


# Module-level hook so tests can monkeypatch without patching httpx directly.
def _get_embedding(text: str, provider: str, model: str) -> list[float]:
    import os
    import httpx

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"input": text, "model": model},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    raise ValueError(f"Unsupported embedding provider '{provider}'")


# Replaceable in tests
get_embedding = _get_embedding


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    target_a_path: str = config.get("target_a", "")
    target_b_template: str = config.get("target_b", "")
    embedding_cfg: dict = config.get("embedding", {})
    provider: str = embedding_cfg.get("provider", "openai")
    model: str = embedding_cfg.get("model", "text-embedding-3-small")
    pass_threshold: float = config.get("pass_threshold", 0.85)

    text_a = resolve_dotpath(target_a_path, context)

    try:
        from jinja2 import Template
        text_b = Template(target_b_template).render(context)
    except Exception:  # noqa: BLE001
        text_b = target_b_template

    try:
        emb_a = get_embedding(text_a, provider, model)
        emb_b = get_embedding(text_b, provider, model)
        similarity = _cosine(emb_a, emb_b)
        passed = similarity >= pass_threshold
        latency_ms = int((time.monotonic() - t0) * 1000)
        return EvaluatorResult(
            score=float(similarity),
            passed=passed,
            reasoning=f"Cosine similarity={similarity:.4f} (threshold={pass_threshold})",
            raw_output={"similarity": similarity},
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        safe = safe_message(exc, fallback="embedding_failed", context="cosine_similarity")
        latency_ms = int((time.monotonic() - t0) * 1000)
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning=f"Embedding error: {safe}",
            raw_output={"error": safe},
            latency_ms=latency_ms,
        )
