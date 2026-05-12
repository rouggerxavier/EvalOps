from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services.usage_service import enforce_quota, increment_usage
from app.domain.services.eval_service import run_evaluation
from app.models import EvaluationRun, EvaluationScore, Project, Rubric, Trace, User
from app.schemas import EvaluationRunOut, EvaluationRunRequest, EvaluationScoreOut

router = APIRouter(prefix="/v1")


def _run_detail(run: EvaluationRun, db: Session) -> dict:
    scores = db.query(EvaluationScore).filter(EvaluationScore.run_id == run.id).all()
    run_out = EvaluationRunOut.model_validate(run).model_dump()
    run_out["scores"] = [EvaluationScoreOut.model_validate(s).model_dump() for s in scores]
    return run_out


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
    # Rubric must belong to the same project
    if rubric.project_id != trace.project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    project = db.get(Project, trace.project_id)
    if project:
        enforce_quota(db, project, "evaluations_run", 1)

    try:
        run = run_evaluation(
            trace_id=payload.trace_id,
            rubric_id=payload.rubric_id,
            triggered_by=payload.triggered_by,
            user_id=user.id,
            db=db,
            rubric_version_num=payload.rubric_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    increment_usage(db, trace.organization_id, evals=1, cost_usd=float(run.cost_usd or 0))
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
