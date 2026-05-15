"""Export service.

Owns the JSONL/NDJSON dump that used to be inline in
``POST /v1/exports``: filter the project's traces, attach human
feedback, write the file, mark the job completed / errored, account
usage and audit. The router stays a thin parse/auth shell.
"""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import exports_dir
from app.domain.services.audit_service import record_audit
from app.domain.services.usage_service import enforce_quota, increment_usage
from app.models import ExportJob, HumanFeedback, Project, Trace, utcnow
from app.schemas import ExportJobCreate
from app.security import new_id


def _filter_traces(db: Session, project_id: str, filters: dict | None) -> list[Trace]:
    query = db.query(Trace).filter(Trace.project_id == project_id)
    filters = filters or {}
    if isinstance(filters.get("environment"), str):
        query = query.filter(Trace.environment == filters["environment"])
    if isinstance(filters.get("status"), str):
        query = query.filter(Trace.status == filters["status"])
    if isinstance(filters.get("name_contains"), str):
        query = query.filter(Trace.name.ilike(f"%{filters['name_contains']}%"))
    return query.order_by(Trace.created_at.asc()).all()


def _serialize_trace(db: Session, trace: Trace) -> dict:
    feedback_rows = (
        db.query(HumanFeedback)
        .filter(HumanFeedback.trace_id == trace.id)
        .order_by(HumanFeedback.created_at.asc())
        .all()
    )
    return {
        "id": trace.id,
        "project_id": trace.project_id,
        "trace_name": trace.name,
        "status": trace.status,
        "environment": trace.environment,
        "tags": trace.tags or {},
        "metadata": trace.metadata_json or {},
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


def create_jsonl_export(
    db: Session,
    project: Project,
    user_id: str,
    payload: ExportJobCreate,
) -> ExportJob:
    """Run the export synchronously and return the persisted job row.

    Raises ``HTTPException(500, export_failed)`` if the file write fails,
    after persisting the ``error`` job row so clients can fetch the cause.
    """
    enforce_quota(db, project, "exports_created", 1)

    job = ExportJob(
        id=new_id("expj"),
        project_id=project.id,
        status="running",
        format=payload.format,
        filters=payload.filters,
        created_by=user_id,
    )
    db.add(job)
    db.flush()

    try:
        traces = _filter_traces(db, project.id, payload.filters)
        out_path = exports_dir() / f"{job.id}.jsonl"
        row_count = 0
        with out_path.open("w", encoding="utf-8") as fh:
            for trace in traces:
                fh.write(json.dumps(_serialize_trace(db, trace), ensure_ascii=False) + "\n")
                row_count += 1
        job.status = "completed"
        job.file_path = str(out_path)
        job.row_count = row_count
        job.expires_at = utcnow() + timedelta(days=7)
        job.completed_at = utcnow()
        increment_usage(db, project.organization_id, exports=1)
        record_audit(
            db, "export.created",
            organization_id=project.organization_id,
            actor_user_id=user_id,
            target_type="project",
            target_id=project.id,
            payload={"export_id": job.id, "rows": row_count},
        )
        db.add(job)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)
        job.completed_at = utcnow()
        db.add(job)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="export_failed",
        ) from exc

    return job
