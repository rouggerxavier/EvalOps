from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.resolver import resolve_dotpath
from app.domain.rubrics.templating import render_template
from app.infra.llm.pricing import estimate_judge_cost_usd
from app.safe_errors import safe_message


def _extract_first_json(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None


# Module-level hook — replace in tests via monkeypatch
def _call_llm(model: str, messages: list[dict], temperature: float) -> str:
    """Call LLM and return raw text response."""
    import httpx

    # Strip provider prefix (e.g. "openai/gpt-4o-mini" → "gpt-4o-mini")
    model_name = model.split("/")[-1] if "/" in model else model

    api_key = os.getenv("OPENAI_API_KEY", "")
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model_name, "messages": messages, "temperature": temperature},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# Replaceable in tests
call_llm = _call_llm


def _render_prompt(template: str, context: dict) -> str:
    try:
        return render_template(template, context)
    except Exception:  # noqa: BLE001
        return template


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    model: str = config.get("model", "openai/gpt-4o-mini")
    temperature: float = config.get("temperature", 0)
    prompt_template: str = config.get("prompt", "")
    retry_on_invalid: int = config.get("retry_on_invalid", 1)
    pass_threshold: float = config.get("pass_threshold", 0.7)
    cost_cap_usd: float = config.get("cost_cap_usd", 0.01)

    # Fix-7B.5 (A-08): assumed completion budget for the pre-call cost estimate.
    # Output length is unknown before the call, so cost is gated conservatively
    # against this budget; post-call the estimate is recomputed from the real
    # response so EvaluationRun.cost_usd / the monthly judge budget see actual
    # (estimated) spend.
    assumed_output_tokens: int = int(config.get("max_output_tokens", 512) or 512)

    rendered_prompt = _render_prompt(prompt_template, context)
    messages = [{"role": "user", "content": rendered_prompt}]

    def _estimated_cost(response_text: str) -> float:
        return float(
            estimate_judge_cost_usd(
                model,
                rendered_prompt,
                response_text,
                assumed_output_tokens=assumed_output_tokens,
            )
        )

    # Fix-7B.5 (A-08): cost_cap_usd is no longer a dead field. Block *before*
    # spending money when even the conservative pre-call estimate exceeds the
    # cap. Error is structured and leaks no stack/SQL/path/secret.
    pre_call_cost = _estimated_cost("")
    if cost_cap_usd is not None and pre_call_cost > float(cost_cap_usd):
        latency_ms = int((time.monotonic() - t0) * 1000)
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning="cost_cap_exceeded",
            raw_output={
                "error": "cost_cap_exceeded",
                "estimated_cost_usd": round(pre_call_cost, 6),
                "cost_cap_usd": round(float(cost_cap_usd), 6),
            },
            cost_usd=pre_call_cost,
            latency_ms=latency_ms,
        )

    raw_text = ""
    parsed: dict | None = None
    attempts = 0
    max_attempts = 1 + retry_on_invalid

    while attempts < max_attempts:
        attempts += 1
        try:
            raw_text = call_llm(model, messages, temperature)
        except Exception as exc:  # noqa: BLE001
            safe = safe_message(exc, fallback="llm_call_failed", context="llm_judge")
            latency_ms = int((time.monotonic() - t0) * 1000)
            return EvaluatorResult(
                score=0.0,
                passed=False,
                reasoning=f"LLM call failed: {safe}",
                raw_output={"error": safe},
                cost_usd=_estimated_cost(raw_text),
                latency_ms=latency_ms,
            )

        # Try strict parse
        try:
            parsed = json.loads(raw_text)
            break
        except json.JSONDecodeError:
            pass

        # Try extract first JSON
        extracted = _extract_first_json(raw_text)
        if extracted:
            try:
                parsed = json.loads(extracted)
                break
            except json.JSONDecodeError:
                pass

        # Retry hint
        if attempts < max_attempts:
            messages.append({"role": "assistant", "content": raw_text})
            messages.append({"role": "user", "content": "Respond ONLY with valid JSON."})

    latency_ms = int((time.monotonic() - t0) * 1000)

    if parsed is None:
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning="LLM returned invalid JSON after retries",
            raw_output={"parse_error": True, "raw": raw_text[:500]},
            cost_usd=_estimated_cost(raw_text),
            latency_ms=latency_ms,
        )

    score = float(parsed.get("score", 0.0))
    score = max(0.0, min(1.0, score))
    passed = score >= pass_threshold
    reasoning = str(parsed.get("reasoning", parsed.get("rationale", "")))

    return EvaluatorResult(
        score=score,
        passed=passed,
        reasoning=reasoning,
        raw_output=parsed,
        cost_usd=_estimated_cost(raw_text),
        latency_ms=latency_ms,
    )
