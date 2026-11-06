from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.domain.services.rag_service import consolidate_rag
from app.db import get_db
from app.deps import get_current_user
from app.domain.services.audit_service import record_audit
from app.workers.queue import get_arq_pool
from app.models import Span, Trace, TraceFlag, User, utcnow
from app.ownership import load_trace
from app.schemas import (
    BulkTraceFlagIn,
    BulkTraceFlagOut,
    RagConsolidatedOut,
    TraceCompareIn,
    TraceCompareOut,
    TraceFlagIn,
    TraceFlagOut,
    TraceOut,
    TraceRerunIn,
    TraceRerunOut,
)
from app.security import new_id

router = APIRouter(prefix="/v1")


def _trace_flag(trace: Trace, user: User, payload: TraceFlagIn) -> TraceFlag:
    return TraceFlag(
        id=new_id("tfl"),
        trace_id=trace.id,
        org_id=trace.organization_id,
        user_id=user.id,
        reason=payload.reason,
        note=payload.note,
    )


_FLAG_DEDUP_WINDOW = timedelta(seconds=10)


def _find_recent_flag(db: Session, trace_id: str, user_id: str, reason: str) -> TraceFlag | None:
    cutoff = utcnow() - _FLAG_DEDUP_WINDOW
    return (
        db.query(TraceFlag)
        .filter(
            TraceFlag.trace_id == trace_id,
            TraceFlag.user_id == user_id,
            TraceFlag.reason == reason,
            TraceFlag.created_at >= cutoff,
        )
        .order_by(TraceFlag.created_at.desc())
        .first()
    )


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _decimal_to_float(value: Decimal | float | int | None) -> float:
    return float(value or 0)


def _span_summary(spans: list[Span]) -> dict[tuple[str, str], dict]:
    summary: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"count": 0, "duration_ms": 0, "errors": 0, "models": set()}
    )
    for span in spans:
        key = (span.type, span.name)
        item = summary[key]
        item["count"] += 1
        item["duration_ms"] += span.duration_ms or 0
        if span.status == "error":
            item["errors"] += 1
        if span.model:
            item["models"].add(span.model)
    return summary


def _compare_spans(left_spans: list[Span], right_spans: list[Span]) -> list[dict]:
    left = _span_summary(left_spans)
    right = _span_summary(right_spans)
    rows = []
    for span_type, name in sorted(set(left) | set(right)):
        left_item = left.get((span_type, name), {"count": 0, "duration_ms": 0, "errors": 0, "models": set()})
        right_item = right.get((span_type, name), {"count": 0, "duration_ms": 0, "errors": 0, "models": set()})
        rows.append(
            {
                "type": span_type,
                "name": name,
                "left_count": left_item["count"],
                "right_count": right_item["count"],
                "duration_delta_ms": right_item["duration_ms"] - left_item["duration_ms"],
                "error_delta": right_item["errors"] - left_item["errors"],
                "left_models": sorted(left_item["models"]),
                "right_models": sorted(right_item["models"]),
            }
        )
    return rows


@router.post(
    "/traces/{trace_id}/flags",
    status_code=status.HTTP_201_CREATED,
    response_model=TraceFlagOut,
)
def flag_trace(
    trace_id: str,
    payload: TraceFlagIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TraceFlag:
    trace = load_trace(db, user.id, trace_id)
    existing = _find_recent_flag(db, trace.id, user.id, payload.reason)
    if existing:
        return existing
    flag = _trace_flag(trace, user, payload)
    db.add(flag)
    record_audit(
        db,
        "trace.flagged",
        organization_id=trace.organization_id,
        actor_user_id=user.id,
        target_type="trace",
        target_id=trace.id,
        payload={"reason": payload.reason, "note": payload.note, "flag_id": flag.id},
    )
    db.commit()
    db.refresh(flag)
    return flag


@router.get("/traces/{trace_id}/rag", response_model=RagConsolidatedOut)
def get_trace_rag(
    trace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    trace = load_trace(db, user.id, trace_id)
    spans = db.query(Span).filter(Span.trace_id == trace.id).order_by(Span.started_at.asc()).all()
    return consolidate_rag(trace, spans)


@router.post(
    "/traces/bulk-flag",
    status_code=status.HTTP_201_CREATED,
    response_model=BulkTraceFlagOut,
)
def bulk_flag_traces(
    payload: BulkTraceFlagIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    flags: list[TraceFlag] = []
    created_ids: list[str] = []
    skipped_ids: list[str] = []
    org_ids: set[str] = set()
    for trace_id in payload.trace_ids:
        trace = load_trace(db, user.id, trace_id)
        existing = _find_recent_flag(db, trace.id, user.id, payload.reason)
        if existing:
            flags.append(existing)
            skipped_ids.append(trace.id)
            continue
        flag = _trace_flag(trace, user, payload)
        db.add(flag)
        flags.append(flag)
        created_ids.append(trace.id)
        org_ids.add(trace.organization_id)
    if created_ids:
        for org_id in org_ids:
            record_audit(
                db,
                "trace.bulk_flagged",
                organization_id=org_id,
                actor_user_id=user.id,
                target_type="trace",
                target_id=created_ids[0],
                payload={
                    "trace_ids": created_ids,
                    "skipped_dedup": skipped_ids,
                    "reason": payload.reason,
                    "note": payload.note,
                },
            )
    db.commit()
    for flag in flags:
        db.refresh(flag)
    return {"data": flags, "created": len(created_ids)}


@router.post("/traces/{trace_id}/rerun", response_model=TraceRerunOut)
async def rerun_trace(
    trace_id: str,
    payload: TraceRerunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    arq_pool=Depends(get_arq_pool),
) -> dict:
    trace = load_trace(db, user.id, trace_id)
    now = utcnow()
    metadata = dict(trace.metadata_json or {})
    metadata.update(
        {
            "replay_of": trace.id,
            "replay_status": "queued",
            "rerun_model": payload.model,
            "rerun_variables": payload.variables,
        }
    )
    new_trace = Trace(
        id=new_id("tr"),
        project_id=trace.project_id,
        organization_id=trace.organization_id,
        client_trace_id=None,
        name=trace.name,
        service=trace.service,
        environment=trace.environment,
        status="partial",
        started_at=now,
        ended_at=now,
        duration_ms=0,
        total_tokens_in=0,
        total_tokens_out=0,
        total_cost_usd=0,
        tags=dict(trace.tags or {}),
        user_ref=trace.user_ref,
        metadata_json=metadata,
    )
    db.add(new_trace)
    new_trace_id = new_trace.id
    original_id = trace.id
    org_id = trace.organization_id
    actor_id = user.id

    try:
        await arq_pool.enqueue_job(
            "replay_trace",
            original_trace_id=original_id,
            new_trace_id=new_trace_id,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="replay_unavailable",
        ) from exc

    record_audit(
        db,
        "trace.rerun_requested",
        organization_id=org_id,
        actor_user_id=actor_id,
        target_type="trace",
        target_id=original_id,
        payload={
            "new_trace_id": new_trace_id,
            "model": payload.model,
            "variables": payload.variables,
        },
    )
    db.commit()
    return {"new_trace_id": new_trace_id, "status": "queued", "replay_status": "queued"}


@router.post("/traces/compare", response_model=TraceCompareOut)
def compare_traces(
    payload: TraceCompareIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    left = load_trace(db, user.id, payload.left_trace_id)
    right = load_trace(db, user.id, payload.right_trace_id)
    if left.project_id != right.project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="trace_project_mismatch")

    left_spans = db.query(Span).filter(Span.trace_id == left.id).all()
    right_spans = db.query(Span).filter(Span.trace_id == right.id).all()
    diff = {
        "status_changed": left.status != right.status,
        "duration_delta_ms": right.duration_ms - left.duration_ms,
        "cost_delta_usd": _decimal_to_float(right.total_cost_usd) - _decimal_to_float(left.total_cost_usd),
        "token_delta": (right.total_tokens_in + right.total_tokens_out)
        - (left.total_tokens_in + left.total_tokens_out),
        "started_delta_seconds": int((_to_utc(right.started_at) - _to_utc(left.started_at)).total_seconds()),
        "spans": _compare_spans(left_spans, right_spans),
    }
    return {
        "left": TraceOut.model_validate(left).model_dump(),
        "right": TraceOut.model_validate(right).model_dump(),
        "diff": diff,
    }
