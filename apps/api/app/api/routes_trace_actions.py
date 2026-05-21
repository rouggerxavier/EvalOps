from collections import defaultdict
from datetime import timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
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


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _pick_span(spans: list[Span], name: str) -> Span | None:
    return next((span for span in spans if span.name == name), None)


def _normalize_citations(source: object) -> list[dict]:
    rows = []
    for index, item in enumerate(_as_list(source), start=1):
        if isinstance(item, str):
            rows.append({"rank": index, "title": None, "score": None, "source": None, "chunk": item})
            continue
        data = _as_dict(item)
        if not data:
            continue
        rows.append(
            {
                "rank": int(_as_number(data.get("rank") or data.get("fonte_n") or data.get("n")) or index),
                "title": _as_string(data.get("title") or data.get("doc_title")),
                "score": _as_number(data.get("score")),
                "source": _as_string(data.get("source") or data.get("doc_ref") or data.get("document_ref")),
                "chunk": _as_string(data.get("chunk") or data.get("chunk_ref") or data.get("text")),
            }
        )
    return rows


def _normalize_claims(source: object) -> list[dict]:
    rows = []
    for item in _as_list(source):
        data = _as_dict(item)
        if not data:
            continue
        text = _as_string(data.get("text") or data.get("claim"))
        if not text:
            continue
        grounded_raw = data.get("grounded")
        rows.append(
            {
                "text": text,
                "grounded": bool(grounded_raw) if isinstance(grounded_raw, bool) else bool(data.get("cite")),
                "cite": _as_string(data.get("cite") or data.get("citation") or data.get("chunk_ref")),
            }
        )
    return rows


def _normalize_claim_links(source: object) -> list[dict]:
    rows = []
    for item in _as_list(source):
        data = _as_dict(item)
        if not data:
            continue
        claim = _as_string(data.get("claim") or data.get("claim_text"))
        chunk = _as_string(data.get("chunk") or data.get("chunk_ref") or data.get("chunk_id"))
        if claim and chunk:
            rows.append({"claim": claim, "chunk": chunk, "score": _as_number(data.get("score"))})
    return rows


def _risk_from_counts(grounded: int, ungrounded: int, avg_score: float | None) -> str:
    total = grounded + ungrounded
    if total and ungrounded / total > 0.5:
        return "high"
    if avg_score is not None and avg_score < 0.5:
        return "high"
    if ungrounded > 0 or (avg_score is not None and avg_score < 0.75):
        return "medium"
    return "low"


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
    flag = _trace_flag(trace, user, payload)
    db.add(flag)
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
    retrieve = _pick_span(spans, "rag.retrieve")
    grounding = _pick_span(spans, "rag.grounding.validate")
    finalize = _pick_span(spans, "response.finalize")
    generate = _pick_span(spans, "llm.generate")

    meta = _as_dict(trace.metadata_json)
    retrieve_out = _as_dict(retrieve.output if retrieve else None)
    grounding_out = _as_dict(grounding.output if grounding else None)
    finalize_out = _as_dict(finalize.output if finalize else None)
    generate_out = _as_dict(generate.output if generate else None)

    citations = (
        _normalize_citations(retrieve_out.get("citations"))
        or _normalize_citations(retrieve_out.get("chunk_refs"))
        or _normalize_citations(grounding_out.get("citations"))
        or _normalize_citations(finalize_out.get("citations"))
        or _normalize_citations(meta.get("citations"))
    )
    claims = (
        _normalize_claims(grounding_out.get("claims"))
        or _normalize_claims(finalize_out.get("claims"))
        or _normalize_claims(meta.get("claims"))
    )
    claim_to_chunk = (
        _normalize_claim_links(grounding_out.get("claim_to_chunk"))
        or _normalize_claim_links(finalize_out.get("claim_to_chunk"))
        or _normalize_claim_links(meta.get("claim_to_chunk"))
    )

    score_values = [row["score"] for row in citations if row.get("score") is not None]
    score_values.extend(row["score"] for row in claim_to_chunk if row.get("score") is not None)
    quality_score = _as_number(grounding_out.get("quality_score") or finalize_out.get("quality_score") or meta.get("quality_score"))
    if quality_score is not None:
        score_values.append(quality_score)
    avg_score = round(sum(score_values) / len(score_values), 4) if score_values else None

    grounded = sum(1 for claim in claims if claim["grounded"])
    ungrounded = sum(1 for claim in claims if not claim["grounded"])
    if not claims:
        unsupported = int(_as_number(grounding_out.get("unsupported_claim_count") or meta.get("unsupported_claim_count")) or 0)
        support_rate = _as_number(grounding_out.get("support_rate") or finalize_out.get("support_rate") or meta.get("support_rate"))
        if support_rate is not None:
            grounded = int(round(support_rate * 10))
            ungrounded = max(unsupported, 10 - grounded)
        else:
            ungrounded = unsupported

    answer_preview = (
        _as_string(finalize_out.get("answer_preview") or finalize_out.get("answer"))
        or _as_string(generate_out.get("answer_preview") or generate_out.get("answer"))
        or _as_string(meta.get("answer_preview"))
    )
    retrieved_docs = int(
        _as_number(retrieve_out.get("retrieved_count") or meta.get("retrieved_count"))
        or len(citations)
    )
    return {
        "retrieved_docs": retrieved_docs,
        "avg_score": avg_score,
        "grounded_claims": grounded,
        "ungrounded_claims": ungrounded,
        "hallucination_risk": _risk_from_counts(grounded, ungrounded, avg_score),
        "answer_preview": answer_preview,
        "citations": citations,
        "claims": claims,
        "claim_to_chunk": claim_to_chunk,
    }


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
    flags = []
    for trace_id in payload.trace_ids:
        trace = load_trace(db, user.id, trace_id)
        flag = _trace_flag(trace, user, payload)
        db.add(flag)
        flags.append(flag)
    db.commit()
    for flag in flags:
        db.refresh(flag)
    return {"data": flags, "created": len(flags)}


@router.post("/traces/{trace_id}/rerun", response_model=TraceRerunOut)
def rerun_trace(
    trace_id: str,
    payload: TraceRerunIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    db.commit()
    return {"new_trace_id": new_trace.id, "status": "queued"}


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
        "started_delta_seconds": int((right.started_at - left.started_at).total_seconds())
        if right.started_at.tzinfo == left.started_at.tzinfo
        else int((right.started_at.replace(tzinfo=timezone.utc) - left.started_at.replace(tzinfo=timezone.utc)).total_seconds()),
        "spans": _compare_spans(left_spans, right_spans),
    }
    return {
        "left": TraceOut.model_validate(left).model_dump(),
        "right": TraceOut.model_validate(right).model_dump(),
        "diff": diff,
    }
