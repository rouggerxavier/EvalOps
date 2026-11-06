"""Trace ingest service.

Holds the heavy lifting that used to live inline in
``POST /v1/traces``: quota pre-checks, span-cap enforcement, idempotency
on ``client_trace_id``, redaction, span/event persistence, parent and
fallback wiring, usage accounting.

The router stays thin: parse → auth → call :func:`ingest_trace_batch` →
return its result.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import max_spans_per_trace
from app.domain.services.redaction_service import (
    redact_event,
    redact_span,
    redact_trace,
    should_redact,
)
from app.domain.services.experiment_service import resolve_prompt_version
from app.domain.services.usage_service import apply_usage_with_quota, enforce_quota
from app.infra.llm.pricing import compute_cost_usd
from app.models import Event, Project, Prompt, Span, Trace
from app.safe_errors import safe_message
from app.schemas import TraceBatchIn
from app.security import new_id


def _enforce_batch_quotas(db: Session, project: Project, payload: TraceBatchIn) -> None:
    """G-07: pre-check trace, span and token monthly quotas atomically."""
    enforce_quota(db, project, "traces_ingested", len(payload.traces))
    total_spans = sum(len(t.spans) for t in payload.traces)
    if total_spans:
        enforce_quota(db, project, "spans_ingested", total_spans)
    total_tokens = sum(
        ((sp.tokens_in or 0) + (sp.tokens_out or 0))
        for t in payload.traces
        for sp in t.spans
    )
    if total_tokens:
        enforce_quota(db, project, "tokens_ingested", total_tokens)


def _enforce_span_cap(payload: TraceBatchIn) -> None:
    cap = max_spans_per_trace()
    for idx, trace_in in enumerate(payload.traces):
        span_count = len(trace_in.spans)
        if span_count > cap:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "too_many_spans",
                    "trace_index": idx,
                    "client_trace_id": trace_in.client_trace_id,
                    "spans": span_count,
                    "limit": cap,
                },
            )


def _existing_trace_id(db: Session, project_id: str, client_trace_id: str | None) -> str | None:
    if not client_trace_id:
        return None
    existing = (
        db.query(Trace)
        .filter(Trace.project_id == project_id, Trace.client_trace_id == client_trace_id)
        .one_or_none()
    )
    if existing is None:
        return None
    if existing.deleted_at is not None:
        # A-05: reingest of a soft-deleted client_trace_id is ambiguous.
        # Contract: reject with a structured 409. We do not recreate a new
        # trace (would collide with uq_traces_project_client) nor auto-restore.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "trace_deleted", "client_trace_id": client_trace_id},
        )
    return existing.id


def _unknown_prompt_ref(db: Session, project_id: str, trace_in: Any) -> str | None:
    """First span ``prompt_version_ref`` that names no prompt of the project, if any."""
    for ref in sorted({s.prompt_version_ref for s in trace_in.spans if s.prompt_version_ref}):
        prompt = db.get(Prompt, ref)
        if prompt is not None and prompt.project_id == project_id:
            continue
        if resolve_prompt_version(ref, project_id, db) is None:
            return ref
    return None


def _persist_trace(
    db: Session,
    project: Project,
    trace_in: Any,
    redact_header: str | None,
) -> tuple[str, int, int, Decimal, int]:
    """Insert one trace + its spans + events. Returns
    ``(trace_id, tokens_in, tokens_out, cost_usd, span_count)``.
    Caller commits.
    """
    if trace_in.ended_at < trace_in.started_at:
        raise ValueError("ended_at must be >= started_at")
    unknown_ref = _unknown_prompt_ref(db, project.id, trace_in)
    if unknown_ref is not None:
        raise ValueError(f"unknown prompt_version_ref: {unknown_ref}")

    do_redact = should_redact(trace_in.tags, redact_header)
    trace_id = new_id("tr")
    duration_ms = int((trace_in.ended_at - trace_in.started_at).total_seconds() * 1000)
    trace_row = Trace(
        id=trace_id,
        project_id=project.id,
        organization_id=project.organization_id,
        client_trace_id=trace_in.client_trace_id,
        name=trace_in.name,
        service=trace_in.service,
        environment=trace_in.environment,
        status=trace_in.status,
        started_at=trace_in.started_at,
        ended_at=trace_in.ended_at,
        duration_ms=duration_ms,
        tags=trace_in.tags,
        user_ref=trace_in.user_ref,
        metadata_json=trace_in.metadata,
        redacted=do_redact,
    )
    if do_redact:
        redact_trace(trace_row)
    db.add(trace_row)
    db.flush()

    client_to_span: dict[str, str] = {}
    parent_refs: list[tuple[Span, str]] = []
    fallback_refs: list[tuple[Span, str]] = []
    total_in = 0
    total_out = 0
    total_cost = Decimal("0")

    for span_in in trace_in.spans:
        if span_in.ended_at < span_in.started_at:
            raise ValueError(f"span '{span_in.client_span_id}' has invalid timestamps")
        span_id = new_id("sp")
        client_to_span[span_in.client_span_id] = span_id
        duration_span_ms = int((span_in.ended_at - span_in.started_at).total_seconds() * 1000)
        if span_in.cost_usd is None:
            cost = compute_cost_usd(span_in.provider, span_in.model, span_in.tokens_in, span_in.tokens_out)
            # `compute_cost_usd` returns 0 for unknown provider/model. Split that
            # zero into "unpriced" (tokens present, no table match) and
            # "unknown" (no tokens at all) so the UI can warn the user that the
            # displayed cost is not a measurement.
            if cost > 0:
                cost_source = "priced"
            elif (span_in.tokens_in or 0) + (span_in.tokens_out or 0) > 0:
                cost_source = "unpriced"
            else:
                cost_source = "unknown"
        else:
            # Client supplied the cost — trust the number, but flag the trace
            # as "provided" so an aggregated total is not confused with a
            # priced-by-table measurement.
            cost = Decimal(str(span_in.cost_usd))
            cost_source = "provided"
        span_metadata = dict(span_in.metadata or {})
        span_metadata["_cost_source"] = cost_source
        row = Span(
            id=span_id,
            trace_id=trace_id,
            parent_span_id=None,
            type=span_in.type,
            name=span_in.name,
            status=span_in.status,
            started_at=span_in.started_at,
            ended_at=span_in.ended_at,
            duration_ms=duration_span_ms,
            provider=span_in.provider,
            model=span_in.model,
            prompt_version_ref=span_in.prompt_version_ref,
            messages_in=span_in.messages_in,
            messages_out=span_in.messages_out,
            tools=span_in.tools,
            tokens_in=span_in.tokens_in,
            tokens_out=span_in.tokens_out,
            cost_usd=float(cost),
            fallback_from_span_id=None,
            input=span_in.input,
            output=span_in.output,
            error=span_in.error,
            metadata_json=span_metadata,
        )
        if do_redact:
            redact_span(row)
        db.add(row)
        if span_in.parent_client_span_id:
            parent_refs.append((row, span_in.parent_client_span_id))
        if span_in.fallback_from_client_span_id:
            fallback_refs.append((row, span_in.fallback_from_client_span_id))
        total_in += span_in.tokens_in or 0
        total_out += span_in.tokens_out or 0
        total_cost += cost
        for event_in in span_in.events:
            event_row = Event(
                id=new_id("ev"),
                span_id=span_id,
                type=event_in.type,
                occurred_at=event_in.occurred_at,
                payload=event_in.payload,
            )
            if do_redact:
                redact_event(event_row)
            db.add(event_row)

    for span_row, parent_client_id in parent_refs:
        parent_id = client_to_span.get(parent_client_id)
        if parent_id is None:
            raise ValueError(f"parent span '{parent_client_id}' not found")
        span_row.parent_span_id = parent_id

    for span_row, fallback_client_id in fallback_refs:
        fallback_id = client_to_span.get(fallback_client_id)
        if fallback_id:
            span_row.fallback_from_span_id = fallback_id

    trace_row.total_tokens_in = total_in
    trace_row.total_tokens_out = total_out
    trace_row.total_cost_usd = float(total_cost)
    db.add(trace_row)
    return trace_id, total_in, total_out, total_cost, len(trace_in.spans)


def ingest_trace_batch(
    db: Session,
    project: Project,
    payload: TraceBatchIn,
    redact_header: str | None,
) -> dict:
    """Persist a batch of traces under ``project`` and return the API response body."""
    _enforce_batch_quotas(db, project, payload)
    _enforce_span_cap(payload)

    results: list[dict] = []
    errors: list[dict] = []

    for idx, trace_in in enumerate(payload.traces):
        try:
            existing_id = _existing_trace_id(db, project.id, trace_in.client_trace_id)
            if existing_id is not None:
                results.append({"client_trace_id": trace_in.client_trace_id, "trace_id": existing_id})
                continue

            trace_id, total_in, total_out, total_cost, span_count = _persist_trace(
                db, project, trace_in, redact_header
            )
            apply_usage_with_quota(
                db,
                project,
                traces=1,
                cost_usd=float(total_cost),
                spans=span_count,
                tokens=total_in + total_out,
            )
            db.commit()
            results.append({"client_trace_id": trace_in.client_trace_id, "trace_id": trace_id})
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append({
                "index": idx,
                "client_trace_id": trace_in.client_trace_id,
                "message": safe_message(exc, fallback="ingest_failed", context="ingest_trace"),
            })

    return {"ingested": len(results), "results": results, "errors": errors}
