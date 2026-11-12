"""Opt-in trace sampling, persisted with ingestion and dispatched by the existing worker."""
from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.services.eval_service import (
    DuplicateEvaluation, JudgeBudgetExhausted, evaluate_trace, existing_run,
    judge_budget_status, rubric_uses_llm_judge,
)
from app.domain.services.trace_lock_service import trace_execution_lock
from app.domain.services.usage_service import enforce_quota
from app.models import EvaluationSamplingConfig, EvaluationSamplingJob, Project, Rubric, RubricVersion, Trace, utcnow

logger = logging.getLogger("evalops.sampling")
TERMINAL_STATUSES = {"completed", "skipped", "blocked", "error", "uncertain"}


def configure_sampling(db: Session, project: Project, settings: dict) -> EvaluationSamplingConfig:
    rubric_id, version = settings["rubric_id"], settings["rubric_version"]
    if bool(rubric_id) != bool(version) or (settings["enabled"] and not rubric_id):
        raise HTTPException(status_code=422, detail="sampling_rubric_required")
    if rubric_id:
        rubric = db.get(Rubric, rubric_id)
        if rubric is None or rubric.project_id != project.id:
            raise HTTPException(status_code=404, detail="not_found")
        if db.query(RubricVersion).filter_by(rubric_id=rubric_id, version=version).first() is None:
            raise HTTPException(status_code=422, detail="rubric_version_not_found")
    # Serializes concurrent first PUTs as well as updates without an upsert dialect.
    db.query(Project).filter_by(id=project.id).with_for_update().one()
    config = db.get(EvaluationSamplingConfig, project.id)
    if config is None:
        config = EvaluationSamplingConfig(project_id=project.id)
        db.add(config)
    for key, value in settings.items():
        setattr(config, key, value)
    config.updated_at = utcnow()
    return config


def select_trace(db: Session, project: Project, trace_id: str, client_trace_id: str | None) -> None:
    """Caller commits selection with the accepted trace, before any queue interaction."""
    config = db.get(EvaluationSamplingConfig, project.id)
    if config is None or not config.enabled or config.percentage <= 0:
        return
    digest = hashlib.sha256(f"{project.id}:{client_trace_id or trace_id}".encode()).digest()
    bucket = int.from_bytes(digest[:8], "big") / 2**64 * 100
    if bucket < config.percentage:
        db.add(EvaluationSamplingJob(
            trace_id=trace_id, project_id=project.id,
            rubric_id=config.rubric_id, rubric_version=config.rubric_version,
        ))


def process_sample(db_factory, trace_id: str) -> dict:
    with db_factory() as db, trace_execution_lock(db, trace_id) as acquired:
        if not acquired:
            return {"status": "busy"}
        job = db.get(EvaluationSamplingJob, trace_id)
        if job is None:
            return {"status": "skipped", "reason": "not_found"}
        if job.status in TERMINAL_STATUSES:
            return {"status": job.status, "run_id": job.run_id, "reason": job.reason}
        if job.status == "started":
            job.status, job.reason = "uncertain", "possible_provider_charge"
            job.updated_at = utcnow()
            db.commit()
            return {"status": job.status, "run_id": job.run_id, "reason": job.reason}
        trace = db.get(Trace, trace_id)
        project = db.get(Project, job.project_id)
        rubric = db.get(Rubric, job.rubric_id)
        version = db.query(RubricVersion).filter_by(rubric_id=job.rubric_id, version=job.rubric_version).one_or_none()
        if (trace is None or trace.deleted_at is not None or project is None or project.archived_at is not None
                or trace.project_id != project.id or rubric is None or rubric.project_id != project.id or version is None):
            job.status, job.reason = "skipped", "not_found"
        else:
            previous = existing_run(db, trace_id, job.rubric_id, job.rubric_version)
            if previous is not None:
                # A manual run is not an automatic completion and is never replaced.
                job.run_id = previous.id
                job.status, job.reason = "skipped", "already_evaluated"
            else:
                attempt_started = False
                try:
                    # These checks do not reserve provider spend; any later failure may have spent money.
                    if rubric_uses_llm_judge(version.id, db):
                        has_budget, spent, budget = judge_budget_status(project.id, db)
                        if not has_budget:
                            raise JudgeBudgetExhausted(spent, budget)
                    enforce_quota(db, project, "evaluations_run", 1)
                    job.status, job.reason = "started", "execution_in_progress"
                    job.execution_attempts += 1
                    job.updated_at = utcnow()
                    db.commit()
                    attempt_started = True
                    run = evaluate_trace(db, trace, rubric, version.version, version.id, project,
                                         triggered_by="sampling", user_id=None)
                    job.run_id = run.id
                    job.status, job.reason = "completed", None
                except DuplicateEvaluation as exc:
                    db.rollback()
                    job = db.get(EvaluationSamplingJob, trace_id)
                    job.run_id = exc.existing_run_id
                    job.status, job.reason = "skipped", "already_evaluated"
                except JudgeBudgetExhausted:
                    db.rollback()
                    job = db.get(EvaluationSamplingJob, trace_id)
                    job.status, job.reason = "blocked", "judge_budget_exhausted"
                except HTTPException as exc:
                    db.rollback()
                    job = db.get(EvaluationSamplingJob, trace_id)
                    if attempt_started:
                        job.status, job.reason = "uncertain", "possible_provider_charge"
                    elif exc.status_code == 402:
                        job.status, job.reason = "blocked", "quota_exceeded"
                    else:
                        job.status, job.reason = "error", "evaluation_failed"
                except Exception as exc:
                    logger.error("sampling.evaluation_failed trace_id=%s", trace_id,
                                 extra={"event": "sampling.evaluation_failed", "error": type(exc).__name__})
                    db.rollback()
                    job = db.get(EvaluationSamplingJob, trace_id)
                    job.status = "uncertain" if attempt_started else "error"
                    job.reason = "possible_provider_charge" if attempt_started else "evaluation_failed"
        job.updated_at = utcnow()
        # Run, usage and link commit together; the earlier started marker protects uncertain provider spend.
        db.commit()
        return {"status": job.status, "run_id": job.run_id, "reason": job.reason}
