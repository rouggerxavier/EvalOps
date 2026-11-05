from __future__ import annotations

import json
import os
import re
import statistics
import time
from typing import Any

from app.domain.evaluators.base import EvaluatorResult
from app.domain.rubrics.templating import render_template
from app.infra.llm import cli_judge
from app.infra.llm.pricing import estimate_judge_cost_usd, split_provider_model
from app.safe_errors import safe_message

#: provider prefix of ``config.model`` -> (OpenAI-compatible base URL, env var with the key)
PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
}


class JudgeNotConfigured(ValueError):
    """Raised before any request: the provider was not called, so nothing was spent."""


def _extract_first_json(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None


# Module-level hook — replace in tests via monkeypatch
def _call_llm(model: str, messages: list[dict], temperature: float) -> str:
    """Call LLM and return raw text response."""
    import httpx

    provider, model_name = split_provider_model(model)
    if provider in cli_judge.CLI_PROVIDERS:
        return cli_judge.call(provider, model_name, messages)
    if provider not in PROVIDERS:
        raise JudgeNotConfigured(f"unsupported_judge_provider:{provider}")
    base_url, key_env = PROVIDERS[provider]
    api_key = os.getenv(key_env, "")
    if not api_key:
        raise JudgeNotConfigured(f"judge_key_not_configured:{key_env}")
    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model_name, "messages": messages, "temperature": temperature},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


# Replaceable in tests
call_llm = _call_llm


def _parse_verdict(raw_text: str) -> tuple[dict, float] | None:
    """Return ``(verdict, score)``, or None when the reply carries no score in 0..1."""
    candidates = [raw_text]
    extracted = _extract_first_json(raw_text)
    if extracted:
        candidates.append(extracted)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            raw_score = parsed["score"]
            if isinstance(raw_score, bool):
                continue
            score = float(raw_score)
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            continue
        if isinstance(parsed, dict) and 0.0 <= score <= 1.0:
            return parsed, score
    return None


def run(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    model = config.get("model")
    if not cli_judge.is_cli_model(model):
        return _run_judge(context, config)
    t0 = time.monotonic()
    provider, model_name = split_provider_model(model)
    identity = {"provider": provider, "model": model_name, "cli_version": None}
    try:
        gate = cli_judge.gate_status(provider)
        if gate:
            raise cli_judge.CliJudgeError(gate)
        identity["cli_version"] = cli_judge.cli_version(provider)
    except cli_judge.CliJudgeError as exc:
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning=f"LLM call failed: {exc}",
            raw_output={"error": str(exc), "judge_cli": identity},
            cost_usd=None,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
    result = _run_judge(context, config)
    result.raw_output = {**result.raw_output, "judge_cli": identity}
    # The plan does not report a price per call: unknown, never 0.
    result.cost_usd = None
    return result


def _run_judge(context: dict, config: dict[str, Any]) -> EvaluatorResult:
    t0 = time.monotonic()
    model: str = config.get("model", "openai/gpt-4o-mini")
    temperature: float = config.get("temperature", 0)
    prompt_template: str = config.get("prompt", "")
    retry_on_invalid: int = config.get("retry_on_invalid", 1)
    pass_threshold: float = config.get("pass_threshold", 0.7)
    cost_cap_usd: float = config.get("cost_cap_usd", 0.01)
    repeats: int = max(1, int(config.get("repeats", 1)))

    # Fix-7B.5 (A-08): assumed completion budget for the pre-call cost estimate.
    # Output length is unknown before the call, so cost is gated conservatively
    # against this budget; post-call the estimate is recomputed from the real
    # response so EvaluationRun.cost_usd / the monthly judge budget see actual
    # (estimated) spend.
    assumed_output_tokens: int = int(config.get("max_output_tokens", 512) or 512)

    def _latency() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        rendered_prompt = render_template(prompt_template, context)
    except Exception as exc:  # noqa: BLE001
        # Judging an unrendered template would produce a score about nothing.
        safe_message(exc, fallback="prompt_render_failed", context="llm_judge")
        return EvaluatorResult(
            score=0.0,
            passed=False,
            reasoning="prompt_render_failed",
            raw_output={"error": "prompt_render_failed"},
            latency_ms=_latency(),
        )

    def _estimated_cost(response_text: str) -> float:
        if cli_judge.is_cli_model(model):
            return 0.0  # no price to cap; run() reports the cost as unknown
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
    pre_call_cost = _estimated_cost("") * repeats
    if cost_cap_usd is not None and pre_call_cost > float(cost_cap_usd):
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
            latency_ms=_latency(),
        )

    total_cost = 0.0
    verdicts: list[dict] = []
    samples: list[float] = []

    for _ in range(repeats):
        messages = [{"role": "user", "content": rendered_prompt}]
        raw_text = ""
        verdict = None
        for attempt in range(1 + retry_on_invalid):
            try:
                raw_text = call_llm(model, messages, temperature)
            except Exception as exc:  # noqa: BLE001
                safe = safe_message(exc, fallback="llm_call_failed", context="llm_judge")
                return EvaluatorResult(
                    score=0.0,
                    passed=False,
                    reasoning=f"LLM call failed: {safe}",
                    raw_output={"error": safe},
                    cost_usd=total_cost if isinstance(exc, JudgeNotConfigured) else total_cost + _estimated_cost(raw_text),
                    latency_ms=_latency(),
                )
            # Every attempt was paid for, not only the one that parsed.
            total_cost += _estimated_cost(raw_text)
            verdict = _parse_verdict(raw_text)
            if verdict is not None:
                break
            if attempt < retry_on_invalid:
                messages.append({"role": "assistant", "content": raw_text})
                messages.append({"role": "user", "content": 'Respond ONLY with valid JSON containing "score" between 0 and 1.'})
        if verdict is None:
            return EvaluatorResult(
                score=0.0,
                passed=False,
                reasoning="LLM returned invalid JSON after retries",
                raw_output={"error": "judge_invalid_response", "parse_error": True, "raw": raw_text[:500]},
                cost_usd=total_cost,
                latency_ms=_latency(),
            )
        verdicts.append(verdict[0])
        samples.append(verdict[1])

    score = sum(samples) / len(samples)
    first = verdicts[0]
    raw_output = first
    if repeats > 1:
        flags = sorted({flag for item in verdicts for flag in _flags(item)})
        raw_output = {**first, "score": score, "flags": flags, "samples": samples, "stddev": statistics.pstdev(samples)}
    return EvaluatorResult(
        score=score,
        passed=score >= pass_threshold,
        reasoning=str(first.get("reasoning", first.get("rationale", ""))),
        raw_output=raw_output,
        cost_usd=total_cost,
        latency_ms=_latency(),
    )


def _flags(verdict: dict) -> list[str]:
    flags = verdict.get("flags")
    return [flag for flag in flags if isinstance(flag, str)] if isinstance(flags, list) else []
