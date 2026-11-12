"""Worker function: replay_trace (Fase B).

Reads the primary LLM span from an original trace, calls the provider via the
existing sync `call_llm` hook (wrapped in `asyncio.to_thread`), and ingests the
response into the placeholder trace created by `rerun_trace`.

State machine on placeholder `metadata_json`:
    queued → running → completed | failed

Decision §B-1: if the original trace has no LLM span, the worker marks
`failed` with `reason="no_llm_span_found"` and returns — never re-raises.
Decision §B-2: variable substitution uses `{{var_name}}`, plain names only.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from arq import Retry

from app.domain.evaluators import llm_judge
from app.domain.services.trace_lock_service import trace_execution_lock
from app.domain.services.usage_service import current_period, get_or_create_counter
from app.infra.llm.pricing import estimate_judge_cost_usd, estimate_tokens, split_provider_model
from app.models import Span, Trace
from app.security import new_id

logger = logging.getLogger("evalops.worker.replay")


class _ReplayResult:
    __slots__ = ("messages_out_text", "tokens_in", "tokens_out", "cost_usd", "duration_ms", "provider", "model")

    def __init__(
        self,
        *,
        messages_out_text: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Decimal,
        duration_ms: int,
        provider: str | None,
        model: str | None,
    ) -> None:
        self.messages_out_text = messages_out_text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost_usd = cost_usd
        self.duration_ms = duration_ms
        self.provider = provider
        self.model = model


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_trace_or_fail(db, trace_id: str) -> Trace:
    trace = db.get(Trace, trace_id)
    if trace is None or trace.deleted_at is not None:
        raise ValueError(f"trace_not_found:{trace_id}")
    return trace


def _find_primary_llm_span(db, trace_id: str) -> Span | None:
    return (
        db.query(Span)
        .filter(Span.trace_id == trace_id)
        .filter((Span.type.in_(("llm_call", "llm"))) | (Span.name.ilike("llm.%")))
        .order_by(Span.started_at.asc())
        .first()
    )


# Completion size assumed when reserving budget before the call (same default as llm_judge).
REPLAY_ASSUMED_OUTPUT_TOKENS = 512
# Same scale as the Numeric(12, 6) cost columns, so reservation and settlement cancel exactly.
_USD = Decimal("0.000001")


def replay_route(provider: str | None, model: str | None, *, override: bool) -> str:
    # The span's provider decides the endpoint: its model id may carry another vendor's prefix.
    return f"{provider}/{model}" if provider and not override else (model or "")


def _prompt_text(messages: list[dict]) -> str:
    return "".join(
        (m.get("content") or "") for m in messages if isinstance(m, dict) and isinstance(m.get("content"), str)
    )


def estimate_replay_reservation(db, original_trace_id: str, rerun_model: str | None, variables: dict) -> Decimal:
    """Budget to hold while the job waits: prompt plus an assumed completion, priced with the A-08 fallback."""
    span = _find_primary_llm_span(db, original_trace_id)
    if span is None:
        return Decimal("0")  # the worker fails with no_llm_span_found before any call
    route = replay_route(span.provider, rerun_model or span.model, override=bool(rerun_model))
    prompt = _prompt_text(_build_messages(span, variables or {}))
    return estimate_judge_cost_usd(route, prompt, assumed_output_tokens=REPLAY_ASSUMED_OUTPUT_TOKENS).quantize(_USD)


def book_replay_cost(db, organization_id: str, period: str, delta: Decimal) -> None:
    """Add ``delta`` to the org's monthly replay spend (row-locked on Postgres); caller commits."""
    if not delta:
        return
    counter = get_or_create_counter(db, organization_id, period, lock=True)
    current = Decimal(str(counter.replay_cost_usd or 0))
    counter.replay_cost_usd = float(max(Decimal("0"), current + delta))
    db.add(counter)


def _book_for(db, trace: Trace, delta: Decimal) -> None:
    book_replay_cost(db, trace.organization_id, current_period(trace.created_at), delta)


_VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}")


def _render(text: str, variables: dict[str, Any]) -> str:
    # Message content can come from end users: never evaluate it as a template.
    return _VARIABLE_RE.sub(
        lambda match: str(variables[match.group(1)]) if match.group(1) in variables else match.group(0),
        text,
    )


def _build_messages(span: Span, variables: dict[str, Any]) -> list[dict]:
    raw = span.messages_in or []
    rendered: list[dict] = []
    for msg in raw:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            content = _render(content, variables)
        rendered.append({**msg, "content": content})
    return rendered


def set_replay_status(
    db,
    trace: Trace,
    status: str,
    *,
    error: str | None = None,
) -> None:
    metadata = dict(trace.metadata_json or {})
    if status == "failed":
        # Nothing was spent (or the real cost was already settled): give the reservation back.
        _book_for(db, trace, -Decimal(str(metadata.pop("replay_reserved_usd", 0) or 0)))
    metadata["replay_status"] = status
    if status == "running" and "replay_started_at" not in metadata:
        metadata["replay_started_at"] = _utcnow().isoformat()
    if status in {"completed", "failed"}:
        metadata["replay_finished_at"] = _utcnow().isoformat()
    if error is not None:
        metadata["replay_error"] = error
    elif status != "failed":
        metadata.pop("replay_error", None)
    trace.metadata_json = metadata
    db.add(trace)
    db.commit()


async def _call_provider(
    provider: str | None,
    model: str | None,
    messages: list[dict],
    *,
    override: bool = False,
) -> _ReplayResult:
    t0 = time.monotonic()
    route = replay_route(provider, model, override=override)

    if route.startswith("cli:"):
        raise llm_judge.JudgeNotConfigured("cli_judge_not_supported_in_replay")

    def _sync() -> str:
        return llm_judge.call_llm(route, messages, 0.0)

    text = await asyncio.to_thread(_sync)
    duration_ms = int((time.monotonic() - t0) * 1000)

    prompt_text = _prompt_text(messages)
    # Record what was actually called; unpriced models use the A-08 fallback, never 0.
    called_provider, called_model = split_provider_model(route)
    return _ReplayResult(
        messages_out_text=text,
        tokens_in=estimate_tokens(prompt_text),
        tokens_out=estimate_tokens(text),
        cost_usd=estimate_judge_cost_usd(route, prompt_text, text).quantize(_USD),
        duration_ms=duration_ms,
        provider=called_provider,
        model=called_model,
    )


def _settle_cost(db, placeholder: Trace, cost: Decimal) -> None:
    """Swap the reservation for the real cost in its own commit, before anything else can fail."""
    metadata = dict(placeholder.metadata_json or {})
    reserved = Decimal(str(metadata.pop("replay_reserved_usd", 0) or 0))
    _book_for(db, placeholder, cost - reserved)
    placeholder.metadata_json = metadata
    placeholder.total_cost_usd = float(cost)
    db.add(placeholder)
    db.commit()


def _ingest_replay_result(
    db,
    placeholder: Trace,
    original_span: Span,
    messages: list[dict],
    result: _ReplayResult,
) -> Span:
    now = _utcnow()
    span = Span(
        id=new_id("sp"),
        trace_id=placeholder.id,
        parent_span_id=None,
        type=original_span.type or "llm_call",
        name=original_span.name or "llm.replay",
        status="ok",
        started_at=now,
        ended_at=now,
        duration_ms=result.duration_ms,
        provider=result.provider,
        model=result.model,
        prompt_version_ref=original_span.prompt_version_ref,
        messages_in=messages,
        messages_out=[{"role": "assistant", "content": result.messages_out_text}],
        tools=None,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=float(result.cost_usd),
        fallback_from_span_id=None,
        input=None,
        output={"text": result.messages_out_text},
        error=None,
        metadata_json={"replay": True, "replay_of_span_id": original_span.id},
    )
    db.add(span)

    placeholder.status = "ok"
    placeholder.duration_ms = result.duration_ms
    placeholder.total_tokens_in = result.tokens_in
    placeholder.total_tokens_out = result.tokens_out
    placeholder.total_cost_usd = float(result.cost_usd)
    placeholder.ended_at = now
    db.add(placeholder)
    db.commit()
    return span


async def replay_trace(ctx: dict, original_trace_id: str, new_trace_id: str) -> dict:
    db_factory = ctx["db_session_factory"]
    logger.info(
        "replay.started",
        extra={"trace_id": new_trace_id, "original": original_trace_id},
    )

    with db_factory() as db, trace_execution_lock(db, [original_trace_id, new_trace_id]) as acquired:
        if not acquired:
            raise Retry(defer=5)
        try:
            placeholder = _load_trace_or_fail(db, new_trace_id)
        except ValueError as exc:
            logger.error("replay.failed", extra={"trace_id": new_trace_id, "reason": str(exc)})
            return {"status": "failed", "reason": str(exc)}
        # A redelivered job must not call the provider again nor rewrite a settled replay.
        if (placeholder.metadata_json or {}).get("replay_status") in {"completed", "failed"}:
            return {"status": placeholder.metadata_json["replay_status"]}
        try:
            original = _load_trace_or_fail(db, original_trace_id)
        except ValueError:
            set_replay_status(db, placeholder, "failed", error="original_trace_not_found")
            logger.error("replay.failed", extra={"trace_id": new_trace_id, "reason": "original_trace_not_found"})
            return {"status": "failed", "reason": "original_trace_not_found"}

        if (original.project_id != placeholder.project_id
                or original.organization_id != placeholder.organization_id):
            set_replay_status(db, placeholder, "failed", error="original_trace_not_found")
            return {"status": "failed", "reason": "original_trace_not_found"}

        set_replay_status(db, placeholder, "running")

        llm_span = _find_primary_llm_span(db, original.id)
        if llm_span is None:
            set_replay_status(db, placeholder, "failed", error="no_llm_span_found")
            logger.error(
                "replay.failed",
                extra={"trace_id": new_trace_id, "reason": "no_llm_span_found"},
            )
            return {"status": "failed", "reason": "no_llm_span_found"}

        metadata = dict(placeholder.metadata_json or {})
        override_model = metadata.get("rerun_model")
        variables = metadata.get("rerun_variables") or {}
        model = override_model or llm_span.model
        messages = _build_messages(llm_span, variables if isinstance(variables, dict) else {})

        llm_span = SimpleNamespace(**{key: getattr(llm_span, key) for key in
                                   ("id", "type", "name", "prompt_version_ref", "provider")})
        db.commit()
        try:
            result = await _call_provider(llm_span.provider, model, messages, override=bool(override_model))
        except Exception as exc:  # noqa: BLE001
            # JudgeNotConfigured carries our own safe codes (unsupported provider, missing key).
            reason = str(exc) if isinstance(exc, llm_judge.JudgeNotConfigured) else type(exc).__name__
            set_replay_status(db, placeholder, "failed", error=reason)
            logger.error(
                "replay.failed",
                extra={"trace_id": new_trace_id, "reason": reason},
            )
            return {"status": "failed", "reason": reason}

        _settle_cost(db, placeholder, result.cost_usd)
        try:
            _ingest_replay_result(db, placeholder, llm_span, messages, result)
            set_replay_status(db, placeholder, "completed")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            set_replay_status(db, placeholder, "failed", error="ingest_failed")
            logger.error("replay.failed", extra={"trace_id": new_trace_id, "reason": "ingest_failed"})
            return {"status": "failed", "reason": "ingest_failed", "error": type(exc).__name__}

    logger.info(
        "replay.completed",
        extra={"trace_id": new_trace_id, "duration_ms": result.duration_ms},
    )
    return {
        "status": "completed",
        "new_trace_id": new_trace_id,
        "duration_ms": result.duration_ms,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
    }
