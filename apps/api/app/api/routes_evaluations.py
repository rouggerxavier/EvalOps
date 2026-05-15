from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services.audit_service import record_audit
from app.domain.services.eval_service import (
    judge_budget_status,
    rubric_uses_llm_judge,
    run_evaluation,
)
from app.domain.services.usage_service import enforce_quota, increment_usage
from app.models import EvaluationRun, EvaluationScore, Project, Rubric, RubricVersion, Trace, User
from app.schemas import EvaluationRunOut, EvaluationRunRequest, EvaluationScoreOut

router = APIRouter(prefix="/v1")


def _run_detail(run: EvaluationRun, db: Session) -> dict:
    scores = db.query(EvaluationScore).filter(EvaluationScore.run_id == run.id).all()
    run_out = EvaluationRunOut.model_validate(run).model_dump()
    run_out["scores"] = [EvaluationScoreOut.model_validate(s).model_dump() for s in scores]
    return run_out


def _existing_run(
    db: Session, trace_id: str, rubric_id: str, rubric_version: int
) -> EvaluationRun | None:
    return (
        db.query(EvaluationRun)
        .filter(
            EvaluationRun.trace_id == trace_id,
            EvaluationRun.rubric_id == rubric_id,
            EvaluationRun.rubric_version == rubric_version,
        )
        .one_or_none()
    )


def _resolve_rubric_version(rubric: Rubric, requested: int | None, db: Session) -> RubricVersion:
    target = requested or rubric.current_version
    version = (
        db.query(RubricVersion)
        .filter(RubricVersion.rubric_id == rubric.id, RubricVersion.version == target)
        .one_or_none()
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rubric_version_not_found",
        )
    return version


@router.post("/evaluations/run", status_code=status.HTTP_201_CREATED)
def trigger_evaluation(
    payload: EvaluationRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    trace = db.get(Trace, payload.trace_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, trace.organization_id)

    rubric = db.get(Rubric, payload.rubric_id)
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if rubric.project_id != trace.project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    rubric_version_row = _resolve_rubric_version(rubric, payload.rubric_version, db)

    # G-11: pre-check the (trace_id, rubric_id, rubric_version) uniqueness.
    # Returning 409 here avoids running the rubric for a duplicate request and
    # surfaces the existing run id so the client can fetch it without retrying.
    existing = _existing_run(db, trace.id, rubric.id, rubric_version_row.version)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "evaluation_run_duplicate",
                "existing_run_id": existing.id,
            },
        )

    project = db.get(Project, trace.project_id)
    if project:
        enforce_quota(db, project, "evaluations_run", 1)

    # G-12: when the rubric uses an llm_judge evaluator, gate at 402 if the
    # plan budget is already exhausted. Per-evaluator budget skipping inside
    # eval_service still applies as a safety net for partial spend during run.
    if rubric_uses_llm_judge(rubric_version_row.id, db):
        has_budget, spent, budget = judge_budget_status(trace.project_id, db)
        if not has_budget:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "judge_budget_exhausted",
                    "spent_usd": round(spent, 6),
                    "budget_usd": round(budget, 6),
                },
            )

    try:
        run = run_evaluation(
            trace_id=payload.trace_id,
            rubric_id=payload.rubric_id,
            triggered_by=payload.triggered_by,
            user_id=user.id,
            db=db,
            rubric_version_num=rubric_version_row.version,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except IntegrityError:
        # G-11: race condition safety net — another request created the row
        # between our pre-check and the insert. Translate to a clean 409.
        db.rollback()
        existing = _existing_run(db, trace.id, rubric.id, rubric_version_row.version)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "evaluation_run_duplicate",
                "existing_run_id": existing.id if existing else None,
            },
        )
    increment_usage(db, trace.organization_id, evals=1, cost_usd=float(run.cost_usd or 0))
    record_audit(
        db, "evaluation.run",
        organization_id=trace.organization_id,
        actor_user_id=user.id,
        target_type="evaluation_run",
        target_id=run.id,
        payload={
            "trace_id": run.trace_id,
            "rubric_id": run.rubric_id,
            "status": run.status,
            "passed": bool(run.passed) if run.passed is not None else None,
        },
    )
    db.commit()

    return {"run": _run_detail(run, db)}


@router.get("/evaluations/{run_id}")
def get_evaluation_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    run = db.get(EvaluationRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    trace = db.get(Trace, run.trace_id)
    ensure_org_membership(db, user.id, trace.organization_id)
    return {"run": _run_detail(run, db)}


@router.get("/projects/{project_id}/evaluations")
def list_project_evaluations(
    project_id: str,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    runs = (
        db.query(EvaluationRun)
        .join(Trace, EvaluationRun.trace_id == Trace.id)
        .filter(Trace.project_id == project_id)
        .order_by(EvaluationRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"data": [_run_detail(run, db) for run in runs]}


@router.get("/traces/{trace_id}/evaluations")
def list_trace_evaluations(
    trace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    trace = db.get(Trace, trace_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, trace.organization_id)
    runs = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.trace_id == trace_id)
        .order_by(EvaluationRun.created_at.desc())
        .all()
    )
    return {"data": [_run_detail(run, db) for run in runs]}
