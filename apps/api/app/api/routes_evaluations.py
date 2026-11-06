from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.domain.services.audit_service import record_audit
from app.domain.services.eval_service import (
    DuplicateEvaluation,
    JudgeBudgetExhausted,
    evaluate_trace,
    existing_run,
    judge_budget_status,
    rubric_uses_llm_judge,
)
from app.domain.services.rubric_report_service import WINDOWS, filtered_traces, rubric_report
from app.infra.llm import cli_judge
from app.models import EvaluationRun, EvaluationScore, Project, Rubric, RubricVersion, Trace, User
from app.ownership import Actor, actor_access, load_project, load_trace, project_access
from app.workers.queue import get_arq_pool
from app.safe_errors import safe_message
from app.schemas import (
    CliJudgeOptionsOut,
    CoverageResponse,
    EvaluationBatchIn,
    EvaluationRunOut,
    EvaluationRunRequest,
    EvaluationScoreOut,
    EvaluationSummaryOut,
)

router = APIRouter(prefix="/v1")


def _run_detail(run: EvaluationRun, db: Session) -> dict:
    scores = db.query(EvaluationScore).filter(EvaluationScore.run_id == run.id).all()
    run_out = EvaluationRunOut.model_validate(run).model_dump()
    run_out["scores"] = [EvaluationScoreOut.model_validate(s).model_dump() for s in scores]
    return run_out


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
    trace = load_trace(db, user.id, payload.trace_id)

    rubric = db.get(Rubric, payload.rubric_id)
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if rubric.project_id != trace.project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    rubric_version_row = _resolve_rubric_version(rubric, payload.rubric_version, db)

    project = load_project(db, user.id, trace.project_id)

    try:
        run = evaluate_trace(
            db,
            trace,
            rubric,
            rubric_version_row.version,
            rubric_version_row.id,
            project,
            triggered_by=payload.triggered_by,
            user_id=user.id,
        )
        db.commit()
    except DuplicateEvaluation as exc:
        # G-11: surfaces the existing run id so the client can fetch it without retrying.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "evaluation_run_duplicate", "existing_run_id": exc.existing_run_id},
        ) from exc
    except JudgeBudgetExhausted as exc:
        # G-12: gate at 402 when the plan's judge budget is already exhausted.
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "judge_budget_exhausted",
                "spent_usd": round(exc.spent_usd, 6),
                "budget_usd": round(exc.budget_usd, 6),
            },
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=safe_message(exc, fallback="invalid_evaluation", context="run_evaluation"),
        ) from exc
    except IntegrityError as exc:
        # G-11: race condition safety net — another request created the row
        # between our pre-check and the insert. Translate to a clean 409.
        db.rollback()
        existing = existing_run(db, trace.id, rubric.id, rubric_version_row.version)
        if existing is None:
            raise exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "evaluation_run_duplicate", "existing_run_id": existing.id},
        ) from exc
    except Exception:
        db.rollback()
        raise

    return {"run": _run_detail(run, db)}


@router.post("/projects/{project_id}/evaluations/batch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_evaluation_batch(
    payload: EvaluationBatchIn,
    project: Project = Depends(project_access("evaluate")),
    db: Session = Depends(get_db),
    arq_pool=Depends(get_arq_pool),
) -> dict:
    """Queue the traces that still lack a complete run. Poll the rubric report for results."""
    rubric = db.get(Rubric, payload.rubric_id)
    if not rubric or rubric.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    version = _resolve_rubric_version(rubric, payload.rubric_version, db)
    if rubric_uses_llm_judge(version.id, db):
        has_budget, spent, budget = judge_budget_status(project.id, db)
        if not has_budget:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"error": "judge_budget_exhausted", "spent_usd": round(spent, 6), "budget_usd": round(budget, 6)},
            )

    complete = db.query(EvaluationRun.trace_id).filter(
        EvaluationRun.rubric_id == rubric.id,
        EvaluationRun.rubric_version == version.version,
        EvaluationRun.status == "completed",
        EvaluationRun.passed.isnot(None),
    )
    traces = filtered_traces(
        db,
        project.id,
        environment=payload.environment,
        batch=payload.batch,
        name_contains=payload.name_contains,
        since=payload.since,
    ).filter(Trace.id.not_in(complete))
    if payload.trace_ids is not None:
        traces = traces.filter(Trace.id.in_(payload.trace_ids))
    trace_ids = [
        row.id for row in traces.with_entities(Trace.id).order_by(Trace.created_at.desc()).limit(payload.limit).all()
    ]

    try:
        for trace_id in trace_ids:
            await arq_pool.enqueue_job(
                "evaluate_trace_job",
                trace_id=trace_id,
                rubric_id=rubric.id,
                rubric_version=version.version,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="evaluation_queue_unavailable",
        ) from exc

    record_audit(
        db, "evaluation.batch_requested",
        organization_id=project.organization_id,
        target_type="rubric",
        target_id=rubric.id,
        payload={"rubric_version": version.version, "enqueued": len(trace_ids), "batch": payload.batch},
    )
    db.commit()
    return {"enqueued": len(trace_ids), "rubric_version": version.version, "trace_ids": trace_ids}


@router.get("/projects/{project_id}/rubrics/{rubric_id}/report")
def get_rubric_report(
    rubric_id: str,
    window: str = Query("30d"),
    environment: str | None = Query(None, pattern=r"^(dev|staging|prod)$"),
    batch: str | None = Query(None, max_length=255),
    project: Project = Depends(project_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    if window not in WINDOWS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_window")
    rubric = db.get(Rubric, rubric_id)
    if not rubric or rubric.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return rubric_report(db, rubric, window=window, environment=environment, batch=batch)


@router.get("/evaluations/{run_id}")
def get_evaluation_run(
    run_id: str,
    actor: Actor = Depends(actor_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    run = db.get(EvaluationRun, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    load_trace(db, actor, run.trace_id)
    return {"run": _run_detail(run, db)}


@router.get("/projects/{project_id}/evaluations")
def list_project_evaluations(
    project_id: str,
    limit: int = 100,
    environment: str | None = Query(None, pattern=r"^(dev|staging|prod)$"),
    actor: Actor = Depends(actor_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    project = load_project(db, actor, project_id)
    query = (
        db.query(EvaluationRun)
        .join(Trace, EvaluationRun.trace_id == Trace.id)
        .filter(Trace.project_id == project.id, Trace.deleted_at.is_(None))
    )
    if environment:
        query = query.filter(Trace.environment == environment)
    runs = query.order_by(EvaluationRun.created_at.desc()).limit(limit).all()
    return {"data": [_run_detail(run, db) for run in runs]}


def _window_days(window: str) -> int:
    if window == "24h":
        return 1
    if window == "30d":
        return 30
    return 7


@router.get("/projects/{project_id}/coverage", response_model=CoverageResponse)
def get_project_coverage(
    project_id: str,
    window: str = Query("7d", pattern=r"^(24h|7d|30d)$"),
    actor: Actor = Depends(actor_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    project = load_project(db, actor, project_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=_window_days(window))
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    total_traces = (
        db.query(func.count(Trace.id))
        .filter(Trace.project_id == project.id, Trace.deleted_at.is_(None), Trace.created_at >= cutoff)
        .scalar()
        or 0
    )
    rubrics = db.query(Rubric).filter(Rubric.project_id == project.id).order_by(Rubric.created_at.desc()).all()
    data = []
    for rubric in rubrics:
        covered = (
            db.query(func.count(func.distinct(EvaluationRun.trace_id)))
            .join(Trace, EvaluationRun.trace_id == Trace.id)
            .filter(
                Trace.project_id == project.id,
                Trace.deleted_at.is_(None),
                Trace.created_at >= cutoff,
                EvaluationRun.rubric_id == rubric.id,
                EvaluationRun.status == "completed",
            )
            .scalar()
            or 0
        )
        runs_7d = (
            db.query(func.count(EvaluationRun.id))
            .filter(
                EvaluationRun.project_id == project.id,
                EvaluationRun.rubric_id == rubric.id,
                EvaluationRun.created_at >= seven_days_ago,
            )
            .scalar()
            or 0
        )
        data.append(
            {
                "rubric_id": rubric.id,
                "rubric_slug": rubric.slug,
                "coverage": round(float(covered) / max(1, int(total_traces)), 4),
                "runs_7d": int(runs_7d),
            }
        )
    return {"data": data}


@router.get("/judges/cli", response_model=CliJudgeOptionsOut)
def list_cli_judges(user: User = Depends(get_current_user)) -> dict:
    return {"data": cli_judge.availability()}


@router.get("/projects/{project_id}/evaluations/summary", response_model=EvaluationSummaryOut)
def get_project_evaluation_summary(
    project_id: str,
    environment: str | None = Query(None, pattern=r"^(dev|staging|prod)$"),
    actor: Actor = Depends(actor_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    project = load_project(db, actor, project_id)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    active_rubrics = db.query(func.count(Rubric.id)).filter(Rubric.project_id == project.id).scalar() or 0
    query = db.query(EvaluationRun).filter(
        EvaluationRun.project_id == project.id, EvaluationRun.created_at >= seven_days_ago
    )
    if environment:
        query = query.join(Trace, EvaluationRun.trace_id == Trace.id).filter(Trace.environment == environment)
    runs = query.all()
    completed = [run for run in runs if run.status == "completed" and run.passed is not None]
    pass_rate = None
    if completed:
        pass_rate = round(sum(1 for run in completed if run.passed) / len(completed), 4)
    cost_usd = sum(float(run.cost_usd or 0) for run in runs)
    all_unknown = not cost_usd and any(run.cost_usd is None for run in runs)
    return {
        "active_rubrics": int(active_rubrics),
        "runs_7d": len(runs),
        "pass_rate": pass_rate,
        "cost_usd": None if all_unknown else round(cost_usd, 6),
    }


@router.get("/traces/{trace_id}/evaluations")
def list_trace_evaluations(
    trace_id: str,
    actor: Actor = Depends(actor_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    trace = load_trace(db, actor, trace_id)
    runs = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.trace_id == trace.id)
        .order_by(EvaluationRun.created_at.desc())
        .all()
    )
    return {"data": [_run_detail(run, db) for run in runs]}
