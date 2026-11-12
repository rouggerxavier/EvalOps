"""Synchronous evaluation service — Phase 4 MVP."""
from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.domain.evaluators.base import EvaluatorResult
from app.domain.evaluators.registry import REGISTRY
from app.domain.rubrics.outcomes import automatic_fail_flags, automatic_failures
from app.domain.rubrics.outcomes import raised_flags as _raised_flags
from app.domain.rubrics.resolver import build_conversation_context, build_trace_context, resolve_dotpath
from app.domain.services.audit_service import record_audit
from app.infra.llm.cli_judge import is_cli_model
from app.domain.services.usage_service import apply_usage_with_quota, current_period, enforce_quota, judge_budget_for_org
from app.models import (
    EvaluationRun,
    EvaluationScore,
    EvaluatorRow,
    ExperimentRun,
    Notification,
    Project,
    Rubric,
    RubricVersion,
    Span,
    Trace,
    UsageCounter,
)
from app.safe_errors import is_safe_public_text, safe_message
from app.security import new_id

# Legacy fallback retained for callers without an org context.
MONTHLY_JUDGE_BUDGET_USD = 20.0
MAX_CONVERSATION_TURNS = 200
NOTIFICATION_DEDUP_WINDOW = timedelta(hours=1)

_EVALUATOR_ERROR_KEYS = ("error", "parse_error", "schema_error")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aggregate(scores: list[tuple[float, float]], method: str) -> float:
    """Aggregate (score, weight) pairs using the given method."""
    if not scores:
        return 0.0
    if method == "weighted_mean":
        total_w = sum(w for _, w in scores)
        if total_w <= 0:
            return 0.0
        return sum(s * w for s, w in scores) / total_w
    if method == "mean":
        return sum(s for s, _ in scores) / len(scores)
    if method == "min":
        return min(s for s, _ in scores)
    if method == "max":
        return max(s for s, _ in scores)
    return 0.0


def _judge_spent_this_month(project_id: str, db: Session) -> float:
    """Judge spend of the whole organization: the budget belongs to the org's plan."""
    now = _utcnow()
    org_projects = (
        db.query(Project.id)
        .filter(Project.organization_id == db.query(Project.organization_id).filter(Project.id == project_id).scalar_subquery())
        .scalar_subquery()
    )
    spent = db.query(func.sum(EvaluationRun.cost_usd)).filter(
        EvaluationRun.project_id.in_(org_projects),
        extract("year", EvaluationRun.created_at) == now.year,
        extract("month", EvaluationRun.created_at) == now.month,
    ).scalar() or 0.0
    # shortcut: a run stopped mid-way keeps no by_variant, so its spend is missed; add a cost column if it matters.
    experiment_runs = db.query(ExperimentRun.by_variant).filter(
        ExperimentRun.project_id.in_(org_projects),
        extract("year", ExperimentRun.created_at) == now.year,
        extract("month", ExperimentRun.created_at) == now.month,
    ).all()
    experiments = sum(
        float(metrics.get("total_cost_usd") or 0)
        for (by_variant,) in experiment_runs
        for metrics in (by_variant or {}).values()
    )
    # Replays call the provider with platform keys; the worker books them on the org's monthly counter.
    replays = db.query(UsageCounter.replay_cost_usd).filter(
        UsageCounter.organization_id == db.query(Project.organization_id).filter(Project.id == project_id).scalar_subquery(),
        UsageCounter.period == current_period(now),
    ).scalar() or 0.0
    return float(spent) + experiments + float(replays)


def _budget_for_project(project_id: str, db: Session) -> float:
    """G-12: judge budget comes from the project's org plan (with safe fallback)."""
    project = db.get(Project, project_id)
    if project is None:
        return MONTHLY_JUDGE_BUDGET_USD
    return judge_budget_for_org(db, project.organization_id)


def _check_judge_budget(project_id: str, db: Session) -> bool:
    """Return True if the project still has remaining judge budget this month."""
    return _judge_spent_this_month(project_id, db) < _budget_for_project(project_id, db)


def judge_budget_status(project_id: str, db: Session) -> tuple[bool, float, float]:
    """Return ``(has_budget, spent_usd, budget_usd)`` for the current month."""
    spent = _judge_spent_this_month(project_id, db)
    budget = _budget_for_project(project_id, db)
    return spent < budget, spent, budget


def _spends_judge_budget(ev_row: EvaluatorRow) -> bool:
    # A local CLI judge bills the user's plan, not the org's judge budget.
    return ev_row.type == "llm_judge" and not is_cli_model((ev_row.config or {}).get("model"))


def rubric_uses_llm_judge(rubric_version_id: str, db: Session) -> bool:
    rows = (
        db.query(EvaluatorRow)
        .filter(
            EvaluatorRow.rubric_version_id == rubric_version_id,
            EvaluatorRow.type == "llm_judge",
            EvaluatorRow.enabled.is_(True),
        )
        .all()
    )
    return any(_spends_judge_budget(row) for row in rows)


def _safe_result_text(value: object, *, fallback: str, context: str) -> str | None:
    if value is None:
        return None
    text = str(value)
    if is_safe_public_text(text):
        return text
    return safe_message(text, fallback=fallback, context=context)


def _sanitize_evaluator_result(result: EvaluatorResult, evaluator_type: str) -> EvaluatorResult:
    """Defense-in-depth before persisting evaluator output.

    Evaluators should sanitize their own failures, but EvaluationScore is a
    public API surface. Guard error-shaped outputs here so a future evaluator
    cannot accidentally persist SQL, stack traces, local paths or secrets.
    """
    raw_output = dict(result.raw_output or {})
    has_error_output = any(key in raw_output for key in _EVALUATOR_ERROR_KEYS)
    if has_error_output:
        for key in _EVALUATOR_ERROR_KEYS:
            if key in raw_output and raw_output[key] not in (None, True, False):
                raw_output[key] = _safe_result_text(
                    raw_output[key],
                    fallback="evaluator_failed",
                    context=f"evaluator_result:{evaluator_type}:{key}",
                )
        result.raw_output = raw_output

    if not result.passed and result.reasoning:
        result.reasoning = _safe_result_text(
            result.reasoning,
            fallback="evaluator_failed",
            context=f"evaluator_result:{evaluator_type}:reasoning",
        ) or "evaluator_failed"

    return result


def _missing_input(ev_row: EvaluatorRow, context: dict) -> str | None:
    """Why this evaluator has nothing to evaluate, or None. Absence of an answer is not a verdict."""
    config = ev_row.config or {}
    target = config.get("target") or config.get("target_a")
    if target:
        return None if resolve_dotpath(target, context).strip() else "empty_target"
    if ev_row.type == "llm_judge" and not context["trace"]["output"]["text"].strip():
        return "no_output"
    return None


def _conversation_context(db: Session, trace: Trace) -> dict:
    conversation_id = (trace.metadata_json or {}).get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return build_conversation_context(None, [])
    # shortcut: filters by JSON inside the project; add an expression index if conversations get large.
    turns = (
        db.query(Trace)
        .filter(
            Trace.project_id == trace.project_id,
            Trace.deleted_at.is_(None),
            Trace.metadata_json["conversation_id"].as_string() == conversation_id,
            Trace.started_at <= trace.started_at,
        )
        .order_by(Trace.started_at.desc())
        .limit(MAX_CONVERSATION_TURNS)
        .all()
    )
    turns.reverse()
    spans_by_trace: dict[str, list[Span]] = {turn.id: [] for turn in turns}
    for span in db.query(Span).filter(Span.trace_id.in_(spans_by_trace)).order_by(Span.started_at.asc()):
        spans_by_trace[span.trace_id].append(span)
    return build_conversation_context(conversation_id, [(turn, spans_by_trace[turn.id]) for turn in turns])


def run_evaluation(
    trace_id: str,
    rubric_id: str,
    triggered_by: str,
    user_id: str,
    db: Session,
    rubric_version_num: int | None = None,
) -> EvaluationRun:
    """Run evaluation synchronously. Returns the completed EvaluationRun.

    The caller owns the final commit/rollback boundary.
    """
    run_start = time.monotonic()

    # Load trace + spans
    trace: Trace | None = db.get(Trace, trace_id)
    if trace is None:
        raise ValueError(f"trace '{trace_id}' not found")

    spans: list[Span] = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.started_at.asc()).all()

    # Load rubric
    rubric: Rubric | None = db.get(Rubric, rubric_id)
    if rubric is None:
        raise ValueError(f"rubric '{rubric_id}' not found")

    target_version = rubric_version_num or rubric.current_version
    rubric_ver: RubricVersion | None = (
        db.query(RubricVersion)
        .filter(RubricVersion.rubric_id == rubric_id, RubricVersion.version == target_version)
        .one_or_none()
    )
    if rubric_ver is None:
        raise ValueError(f"rubric version {target_version} not found")

    # Keep the run and scores in memory until provider calls finish.
    run = EvaluationRun(
        id=new_id("evr"),
        project_id=trace.project_id,
        trace_id=trace_id,
        rubric_id=rubric_id,
        rubric_version=target_version,
        triggered_by=triggered_by,
        status="running",
        started_at=_utcnow(),
        cost_usd=0.0,
        run_metadata={},
    )
    project_id = trace.project_id

    # Build trace context for evaluators
    context = build_trace_context(trace, spans)
    context["trace"]["conversation"] = _conversation_context(db, trace)
    context = deepcopy(context)

    # Load evaluator rows ordered by ord
    evaluator_rows: list[EvaluatorRow] = (
        db.query(EvaluatorRow)
        .filter(EvaluatorRow.rubric_version_id == rubric_ver.id, EvaluatorRow.enabled == True)  # noqa: E712
        .order_by(EvaluatorRow.ord)
        .all()
    )

    evaluator_rows = [
        SimpleNamespace(**{key: deepcopy(getattr(row, key)) for key in
                           ("id", "type", "config", "slug", "weight", "fail_fast")})
        for row in evaluator_rows
    ]
    parsed_spec: dict = deepcopy(rubric_ver.parsed_spec or {})
    db.commit()  # Materialized inputs: providers run without a database transaction.
    aggregate_method: str = parsed_spec.get("aggregate", "weighted_mean")
    fail_fast_global: bool = parsed_spec.get("fail_fast", False)
    auto_fail_conditions: list[dict] = parsed_spec.get("automatic_fail_conditions", [])
    auto_fail_flags = automatic_fail_flags(parsed_spec)

    score_records: list[EvaluationScore] = []
    total_cost = 0.0
    cost_unknown = False
    should_break = False

    for ev_row in evaluator_rows:
        if should_break:
            break

        # Budget guard for llm_judge
        if _spends_judge_budget(ev_row):
            has_budget = _check_judge_budget(project_id, db)
            db.commit()
            if not has_budget:
                err_score = EvaluationScore(
                    id=new_id("evs"),
                    run_id=run.id,
                    evaluator_row_id=ev_row.id,
                    evaluator_slug=ev_row.slug,
                    score=0.0,
                    passed=False,
                    reasoning="judge_budget_exhausted",
                    raw_output={"error": "judge_budget_exhausted"},
                    cost_usd=0.0,
                    latency_ms=0,
                )
                score_records.append(err_score)
                continue

        missing = _missing_input(ev_row, context)
        try:
            if missing:
                result = EvaluatorResult(score=0.0, passed=False, reasoning=missing, raw_output={"error": missing})
            else:
                result: EvaluatorResult = REGISTRY[ev_row.type](context, ev_row.config)
                result = _sanitize_evaluator_result(result, ev_row.type)
        except Exception as exc:  # noqa: BLE001
            safe = safe_message(
                exc, fallback="evaluator_failed", context=f"evaluator:{ev_row.type}"
            )
            result = EvaluatorResult(
                score=0.0,
                passed=False,
                reasoning=f"Evaluator error: {safe}",
                raw_output={"error": safe},
            )

        score_rec = EvaluationScore(
            id=new_id("evs"),
            run_id=run.id,
            evaluator_row_id=ev_row.id,
            evaluator_slug=ev_row.slug,
            score=result.score,
            passed=result.passed,
            reasoning=result.reasoning,
            raw_output=result.raw_output,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
        )
        score_records.append(score_rec)
        if result.cost_usd is None:
            cost_unknown = True
        else:
            total_cost += result.cost_usd

        # fail_fast logic
        if (ev_row.fail_fast or fail_fast_global) and not result.passed:
            should_break = True

    # An evaluator that could not run says nothing about quality: it stays out
    # of the score, and the verdict is unknown instead of a failure.
    weight_map = {er.slug: er.weight for er in evaluator_rows}
    usable = [sr for sr in score_records if not (sr.raw_output or {}).get("error")]
    errored = [sr for sr in score_records if (sr.raw_output or {}).get("error")]
    aggregate_score = (
        _aggregate([(float(sr.score), weight_map.get(sr.evaluator_slug, 1.0)) for sr in usable], aggregate_method)
        if usable
        else None
    )
    threshold = float(parsed_spec.get("threshold", 0.7))

    # Check automatic_fail_conditions
    raised_flags = _raised_flags(usable) & auto_fail_flags
    auto_failed = bool(raised_flags) or bool(automatic_failures(usable, auto_fail_conditions))

    # JSON columns do not track in-place changes: this dict is assigned once, below.
    metadata = dict(run.run_metadata or {})
    if raised_flags:
        metadata["raised_flags"] = sorted(raised_flags)
    if auto_failed:
        metadata["auto_failed"] = True

    # Determine final status
    if not score_records:
        status = "error"
        run.error_json = {"code": "no_evaluators_ran"}
        passed = None
    elif not usable:
        status = "error"
        run.error_json = {
            "code": "all_evaluators_failed",
            "reasons": sorted({str((sr.raw_output or {}).get("error")) for sr in errored}),
        }
        passed = None
    else:
        status = "completed"
        if errored:
            metadata["partial_failure"] = True
            passed = False if auto_failed else None
        else:
            passed = aggregate_score >= threshold and not auto_failed

    run.status = status
    run.aggregate_score = aggregate_score
    run.passed = passed
    if cost_unknown:
        metadata["cost_unknown"] = True
    # Known spend still counts toward the budget; only all-unknown is NULL.
    run.cost_usd = None if cost_unknown and not total_cost else total_cost
    run.run_metadata = metadata
    run.completed_at = _utcnow()
    run.latency_ms = int((time.monotonic() - run_start) * 1000)

    run.scores = score_records
    return run


class DuplicateEvaluation(Exception):
    """A finished run already exists for this trace, rubric and version."""

    def __init__(self, existing_run_id: str) -> None:
        super().__init__(existing_run_id)
        self.existing_run_id = existing_run_id


class JudgeBudgetExhausted(Exception):
    def __init__(self, spent_usd: float, budget_usd: float) -> None:
        super().__init__("judge_budget_exhausted")
        self.spent_usd = spent_usd
        self.budget_usd = budget_usd


def existing_run(db: Session, trace_id: str, rubric_id: str, rubric_version: int) -> EvaluationRun | None:
    return (
        db.query(EvaluationRun)
        .filter(
            EvaluationRun.trace_id == trace_id,
            EvaluationRun.rubric_id == rubric_id,
            EvaluationRun.rubric_version == rubric_version,
        )
        .one_or_none()
    )


def _notify_problem(db: Session, run: EvaluationRun, rubric: Rubric) -> None:
    metadata = run.run_metadata or {}
    if run.status == "error":
        kind, title = "err", f"Avaliação com erro: {rubric.slug}"
    elif metadata.get("auto_failed"):
        kind, title = "err", f"Falha crítica na rubrica {rubric.slug}"
    elif metadata.get("partial_failure"):
        kind, title = "warn", f"Avaliação parcial: {rubric.slug}"
    else:
        return
    # One per rubric and problem per hour: a bad batch must not bury the rest.
    recent = db.query(Notification.id).filter(
        Notification.project_id == run.project_id,
        Notification.title == title,
        Notification.created_at >= _utcnow() - NOTIFICATION_DEDUP_WINDOW,
    ).first()
    if recent is None:
        db.add(
            Notification(
                id=new_id("ntf"),
                project_id=run.project_id,
                kind=kind,
                title=title,
                meta={"trace_id": run.trace_id, "run_id": run.id, "rubric_id": run.rubric_id},
            )
        )


def evaluate_trace(
    db: Session,
    trace: Trace,
    rubric: Rubric,
    rubric_version: int,
    version_id: str,
    project: Project,
    *,
    triggered_by: str,
    user_id: str | None,
) -> EvaluationRun:
    """Evaluate one trace with its checks and accounting. The caller commits.

    Usage is applied only after the evaluators: it locks the org's usage row on
    Postgres and ingestion waits on that row, so it must not stay locked during
    judge calls. The commit below only releases rows the quota check may create.

    A run that errored or finished partially is replaced, keeping what it spent;
    a complete run raises :class:`DuplicateEvaluation`.
    """
    previous = existing_run(db, trace.id, rubric.id, rubric_version)
    if previous is not None and previous.status != "error" and not (previous.run_metadata or {}).get("partial_failure"):
        raise DuplicateEvaluation(previous.id)

    if rubric_uses_llm_judge(version_id, db):
        has_budget, spent, budget = judge_budget_status(trace.project_id, db)
        if not has_budget:
            raise JudgeBudgetExhausted(spent, budget)

    enforce_quota(db, project, "evaluations_run", 1)

    previous_cost = 0.0
    attempt = 1
    if previous is not None:
        previous_cost = float(previous.cost_usd or 0)  # NULL adds nothing, and stays NULL below
        attempt = int((previous.run_metadata or {}).get("attempt", 1)) + 1
    previous_id = previous.id if previous is not None else None
    trace_id, rubric_id = trace.id, rubric.id
    db.commit()

    run = run_evaluation(
        trace_id=trace_id,
        rubric_id=rubric_id,
        triggered_by=triggered_by,
        user_id=user_id or "",
        db=db,
        rubric_version_num=rubric_version,
    )
    if previous_id is not None:
        with db.no_autoflush:
            previous = db.get(EvaluationRun, previous_id)
            db.delete(previous)
            db.flush()
    db.add(run)
    apply_usage_with_quota(db, project, evals=1, cost_usd=float(run.cost_usd or 0))
    if previous is not None:
        if run.cost_usd is not None or previous_cost:
            run.cost_usd = float(run.cost_usd or 0) + previous_cost
        run.run_metadata = {**(run.run_metadata or {}), "attempt": attempt}
    _notify_problem(db, run, rubric)
    record_audit(
        db, "evaluation.run",
        organization_id=trace.organization_id,
        actor_user_id=user_id,
        target_type="evaluation_run",
        target_id=run.id,
        payload={
            "trace_id": run.trace_id,
            "rubric_id": run.rubric_id,
            "status": run.status,
            "passed": bool(run.passed) if run.passed is not None else None,
        },
    )
    db.flush()
    return run
