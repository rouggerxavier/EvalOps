"""Worker function: evaluate_trace_job, one trace of a batch evaluation."""
from __future__ import annotations

import asyncio
import logging

from arq import Retry
from fastapi import HTTPException

from app.domain.services.eval_service import DuplicateEvaluation, JudgeBudgetExhausted, evaluate_trace
from app.domain.services.trace_lock_service import trace_execution_lock
from app.models import Project, Rubric, RubricVersion, Trace

logger = logging.getLogger("evalops.worker.evaluation")


def _evaluate(db_factory, trace_id: str, rubric_id: str, rubric_version: int, triggered_by: str) -> dict:
    with db_factory() as db, trace_execution_lock(db, trace_id) as acquired:
        if not acquired:
            return {"status": "busy"}
        trace = db.get(Trace, trace_id)
        rubric = db.get(Rubric, rubric_id)
        version = (
            db.query(RubricVersion)
            .filter(RubricVersion.rubric_id == rubric_id, RubricVersion.version == rubric_version)
            .one_or_none()
        )
        if trace is None or rubric is None or version is None or trace.deleted_at is not None:
            return {"status": "skipped", "reason": "not_found"}
        project = db.get(Project, trace.project_id)
        if project is None or project.archived_at is not None or rubric.project_id != trace.project_id:
            return {"status": "skipped", "reason": "not_found"}
        try:
            run = evaluate_trace(
                db, trace, rubric, version.version, version.id, project, triggered_by=triggered_by, user_id=None
            )
            db.commit()
        except DuplicateEvaluation:
            db.rollback()
            return {"status": "skipped", "reason": "already_evaluated"}
        except JudgeBudgetExhausted:
            db.rollback()
            return {"status": "skipped", "reason": "judge_budget_exhausted"}
        except HTTPException as exc:
            db.rollback()
            if exc.status_code == 402:
                return {"status": "skipped", "reason": "quota_exceeded"}
            raise
        return {"status": run.status, "run_id": run.id}


async def evaluate_trace_job(
    ctx: dict,
    trace_id: str,
    rubric_id: str,
    rubric_version: int,
    triggered_by: str = "batch",
) -> dict:
    result = await asyncio.to_thread(
        _evaluate, ctx["db_session_factory"], trace_id, rubric_id, rubric_version, triggered_by
    )
    if result["status"] == "busy":
        raise Retry(defer=5)
    logger.info("evaluation.job_done", extra={"trace_id": trace_id, "status": result["status"]})
    return result
