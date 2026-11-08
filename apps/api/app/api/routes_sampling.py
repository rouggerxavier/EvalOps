from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.services.audit_service import record_audit
from app.domain.services.sampling_service import configure_sampling
from app.models import EvaluationSamplingConfig, EvaluationSamplingJob, Project, utcnow
from app.ownership import project_access
from app.schemas import EvaluationSamplingConfigOut, EvaluationSamplingJobOut, EvaluationSamplingRetryIn, EvaluationSamplingSettings

router = APIRouter(prefix="/v1/projects/{project_id}/evaluation-sampling")


@router.get("", response_model=EvaluationSamplingConfigOut)
def get_sampling(project: Project = Depends(project_access("read")), db: Session = Depends(get_db)):
    return db.get(EvaluationSamplingConfig, project.id) or EvaluationSamplingConfigOut()


@router.put("", response_model=EvaluationSamplingConfigOut)
def put_sampling(payload: EvaluationSamplingSettings, project: Project = Depends(project_access("evaluate")),
                 db: Session = Depends(get_db)):
    config = configure_sampling(db, project, payload.model_dump())
    record_audit(db, "evaluation.sampling_configured", organization_id=project.organization_id,
                 target_type="project", target_id=project.id, payload=payload.model_dump())
    db.commit()
    return config


@router.get("/jobs")
def list_sampling_jobs(limit: int = Query(100, ge=1, le=100),
                       project: Project = Depends(project_access("read")), db: Session = Depends(get_db)):
    jobs = db.query(EvaluationSamplingJob).filter_by(project_id=project.id).order_by(
        EvaluationSamplingJob.created_at.desc(), EvaluationSamplingJob.trace_id).limit(limit).all()
    return {"data": [EvaluationSamplingJobOut.model_validate(job).model_dump() for job in jobs]}


@router.post("/jobs/{trace_id}/retry", response_model=EvaluationSamplingJobOut)
def retry_sampling_job(trace_id: str, payload: EvaluationSamplingRetryIn | None = None,
                       project: Project = Depends(project_access("evaluate")),
                       db: Session = Depends(get_db)):
    job = db.query(EvaluationSamplingJob).filter_by(project_id=project.id, trace_id=trace_id).with_for_update().one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="not_found")
    if job.status not in {"blocked", "error", "queue_error", "uncertain"}:
        raise HTTPException(status_code=409, detail="sampling_job_not_retryable")
    if job.status == "uncertain" and not (payload and payload.confirm_possible_charge):
        raise HTTPException(status_code=409, detail={
            "error": "sampling_retry_requires_cost_confirmation",
            "warning": EvaluationSamplingJobOut.model_validate(job).retry_warning,
        })
    record_audit(db, "evaluation.sampling_retry_requested", organization_id=project.organization_id,
                 target_type="trace", target_id=trace_id,
                 payload={"previous_status": job.status, "confirm_possible_charge": bool(payload and payload.confirm_possible_charge)})
    job.status, job.reason = "pending", None
    job.next_attempt_at = job.updated_at = utcnow()
    db.commit()
    return job
