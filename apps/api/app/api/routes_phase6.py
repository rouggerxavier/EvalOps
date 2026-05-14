from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import exports_dir
from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services.usage_service import (
    current_period,
    enforce_quota,
    ensure_subscription,
    get_or_create_counter,
    increment_usage,
)
from app.models import AuditLog, ExportJob, HumanFeedback, Plan, Project, Subscription, Trace, User, utcnow
from app.schemas import ExportJobCreate, ExportJobOut, HumanFeedbackCreate, HumanFeedbackOut
from app.security import new_id

router = APIRouter(prefix="/v1")


def _trace_or_404(trace_id: str, user_id: str, db: Session) -> Trace:
    trace = db.get(Trace, trace_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user_id, trace.organization_id)
    return trace


def _project_or_404(project_id: str, user_id: str, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user_id, project.organization_id)
    return project


@router.post("/traces/{trace_id}/feedback", status_code=status.HTTP_201_CREATED)
def create_feedback(
    trace_id: str,
    payload: HumanFeedbackCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    trace = _trace_or_404(trace_id, user.id, db)
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
    trace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    trace = _trace_or_404(trace_id, user.id, db)
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
    project = _project_or_404(payload.project_id, user.id, db)
    enforce_quota(db, project, "exports_created", 1)

    job = ExportJob(
        id=new_id("expj"),
        project_id=project.id,
        status="running",
        format=payload.format,
        filters=payload.filters,
        created_by=user.id,
    )
    db.add(job)
    db.flush()

    try:
        query = db.query(Trace).filter(Trace.project_id == project.id)
        filters = payload.filters or {}
        if isinstance(filters.get("environment"), str):
            query = query.filter(Trace.environment == filters["environment"])
        if isinstance(filters.get("status"), str):
            query = query.filter(Trace.status == filters["status"])
        if isinstance(filters.get("name_contains"), str):
            query = query.filter(Trace.name.ilike(f"%{filters['name_contains']}%"))
        traces = query.order_by(Trace.created_at.asc()).all()

        out_dir = exports_dir()
        out_path = out_dir / f"{job.id}.jsonl"
        row_count = 0
        with out_path.open("w", encoding="utf-8") as fh:
            for tr in traces:
                feedback_rows = (
                    db.query(HumanFeedback)
                    .filter(HumanFeedback.trace_id == tr.id)
                    .order_by(HumanFeedback.created_at.asc())
                    .all()
                )
                item = {
                    "id": tr.id,
                    "project_id": tr.project_id,
                    "trace_name": tr.name,
                    "status": tr.status,
                    "environment": tr.environment,
                    "tags": tr.tags or {},
                    "metadata": tr.metadata_json or {},
                    "feedback": [
                        {
                            "id": fb.id,
                            "source": fb.source,
                            "thumbs": fb.thumbs,
                            "rating": fb.rating,
                            "comment": fb.comment,
                            "tags": fb.tags or [],
                            "created_at": fb.created_at.isoformat(),
                        }
                        for fb in feedback_rows
                    ],
                }
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                row_count += 1
        job.status = "completed"
        job.file_path = str(out_path)
        job.row_count = row_count
        job.expires_at = utcnow() + timedelta(days=7)
        job.completed_at = utcnow()
        increment_usage(db, project.organization_id, exports=1)
        db.add(
            AuditLog(
                id=new_id("adt"),
                organization_id=project.organization_id,
                actor_user_id=user.id,
                action="export.created",
                target_type="project",
                target_id=project.id,
                payload={"export_id": job.id, "rows": row_count},
            )
        )
        db.add(job)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)
        job.completed_at = utcnow()
        db.add(job)
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="export_failed") from exc

    return {"export_id": job.id, "status": job.status}


@router.get("/exports/{export_id}")
def get_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExportJobOut:
    job = db.get(ExportJob, export_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, job.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    return ExportJobOut.model_validate(job)


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the JSONL/NDJSON file for a completed export (G-09)."""
    job = db.get(ExportJob, export_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    project = db.get(Project, job.project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)

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
        "cost_usd": float(row.cost_usd or 0),
    }
