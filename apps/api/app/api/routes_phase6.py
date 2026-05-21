from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services.export_service import create_jsonl_export
from app.domain.services.usage_service import (
    current_period,
    ensure_subscription,
    get_or_create_counter,
)
from app.models import AuditLog, ExportJob, HumanFeedback, Plan, Trace, User, utcnow
from app.ownership import get_owned_trace, load_export, load_project
from app.schemas import ExportJobCreate, ExportJobOut, ExportListResponse, HumanFeedbackCreate, HumanFeedbackOut
from app.security import new_id

router = APIRouter(prefix="/v1")


@router.post("/traces/{trace_id}/feedback", status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: HumanFeedbackCreate,
    trace: Trace = Depends(get_owned_trace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if payload.thumbs is None and payload.rating is None and (payload.comment or "").strip() == "":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="feedback_empty")
    row = HumanFeedback(
        id=new_id("fbk"),
        trace_id=trace.id,
        source=payload.source,
        thumbs=payload.thumbs,
        rating=payload.rating,
        comment=payload.comment,
        tags=payload.tags,
        user_ref=payload.user_ref,
        correction=payload.correction,
    )
    db.add(row)
    db.add(
        AuditLog(
            id=new_id("adt"),
            organization_id=trace.organization_id,
            actor_user_id=user.id,
            action="feedback.created",
            target_type="trace",
            target_id=trace.id,
            payload={"feedback_id": row.id},
        )
    )
    db.commit()
    db.refresh(row)
    return {"feedback": HumanFeedbackOut.model_validate(row).model_dump()}


@router.get("/traces/{trace_id}/feedback")
def list_feedback(
    trace: Trace = Depends(get_owned_trace),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(HumanFeedback)
        .filter(HumanFeedback.trace_id == trace.id)
        .order_by(HumanFeedback.created_at.desc())
        .all()
    )
    return {"data": [HumanFeedbackOut.model_validate(row).model_dump() for row in rows]}


@router.post("/exports", status_code=status.HTTP_202_ACCEPTED)
def create_export(
    payload: ExportJobCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = load_project(db, user.id, payload.project_id)
    job = create_jsonl_export(db, project, user.id, payload)
    return {"export_id": job.id, "status": job.status}


@router.get("/projects/{project_id}/exports", response_model=ExportListResponse)
def list_project_exports(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = load_project(db, user.id, project_id)
    rows = (
        db.query(ExportJob)
        .filter(ExportJob.project_id == project.id)
        .order_by(ExportJob.created_at.desc(), ExportJob.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "data": [ExportJobOut.model_validate(row).model_dump() for row in rows],
        "next_cursor": rows[-1].id if has_more and rows else None,
    }


@router.get("/exports/{export_id}")
def get_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExportJobOut:
    job, _ = load_export(db, user.id, export_id)
    return ExportJobOut.model_validate(job)


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the JSONL/NDJSON file for a completed export (G-09)."""
    job, _ = load_export(db, user.id, export_id)

    if job.expires_at is not None:
        exp = job.expires_at
        now = utcnow()
        # SQLite may return naive datetimes; normalise before comparing.
        if exp.tzinfo is None:
            now = now.replace(tzinfo=None)
        if now > exp:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="export_expired")

    if job.status != "completed" or not job.file_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="export_not_ready",
        )

    file_path = Path(job.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="export_file_missing")

    return FileResponse(
        path=str(file_path),
        media_type="application/x-ndjson",
        filename=f"export-{export_id}.jsonl",
    )


@router.get("/organizations/{org_id}/subscription")
def get_subscription(
    org_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ensure_org_membership(db, user.id, org_id)
    sub = ensure_subscription(db, org_id)
    plan = db.get(Plan, sub.plan_id)
    db.commit()
    return {
        "organization_id": org_id,
        "subscription": {
            "id": sub.id,
            "status": sub.status,
            "started_at": sub.started_at,
            "ends_at": sub.ends_at,
        },
        "plan": {
            "id": plan.id if plan else None,
            "code": plan.code if plan else "free",
            "name": plan.name if plan else "Free",
            "monthly_trace_limit": int(plan.monthly_trace_limit) if plan else 1000,
            "monthly_eval_limit": int(plan.monthly_eval_limit) if plan else 500,
            "monthly_export_limit": int(plan.monthly_export_limit) if plan else 10,
            "monthly_span_limit": int(plan.monthly_span_limit) if plan else 50_000,
            "monthly_token_limit": int(plan.monthly_token_limit) if plan else 5_000_000,
            "monthly_judge_budget_usd": float(plan.monthly_judge_budget_usd) if plan else 20.0,
        },
    }


@router.get("/organizations/{org_id}/usage")
def get_usage(
    org_id: str,
    period: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ensure_org_membership(db, user.id, org_id)
    if period is None:
        period = current_period()
    row = get_or_create_counter(db, org_id, period)
    db.commit()
    return {
        "organization_id": org_id,
        "period": period,
        "traces_ingested": int(row.traces_ingested or 0),
        "evaluations_run": int(row.evaluations_run or 0),
        "exports_created": int(row.exports_created or 0),
        "spans_ingested": int(row.spans_ingested or 0),
        "tokens_ingested": int(row.tokens_ingested or 0),
        "cost_usd": float(row.cost_usd or 0),
    }
