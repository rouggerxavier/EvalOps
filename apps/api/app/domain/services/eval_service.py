"""Synchronous evaluation service — Phase 4 MVP."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.domain.evaluators.base import EvaluatorResult
from app.domain.evaluators.registry import REGISTRY
from app.domain.rubrics.resolver import build_trace_context
from app.domain.services.usage_service import judge_budget_for_org
from app.models import EvaluationRun, EvaluationScore, EvaluatorRow, Project, Rubric, RubricVersion, Span, Trace
from app.safe_errors import is_safe_public_text, safe_message
from app.security import new_id

# Legacy fallback retained for callers without an org context.
MONTHLY_JUDGE_BUDGET_USD = 20.0

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
    now = _utcnow()
    spent = db.query(func.sum(EvaluationRun.cost_usd)).filter(
        EvaluationRun.project_id == project_id,
        extract("year", EvaluationRun.created_at) == now.year,
        extract("month", EvaluationRun.created_at) == now.month,
    ).scalar() or 0.0
    return float(spent)


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


def rubric_uses_llm_judge(rubric_version_id: str, db: Session) -> bool:
    return (
        db.query(EvaluatorRow.id)
        .filter(
            EvaluatorRow.rubric_version_id == rubric_version_id,
            EvaluatorRow.type == "llm_judge",
            EvaluatorRow.enabled.is_(True),
        )
        .first()
        is not None
    )


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

    spans: list[Span] = db.query(Span).filter(Span.trace_id == trace_id).all()

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

    # Create the run record
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
    db.add(run)
    db.flush()  # get run.id without committing

    # Build trace context for evaluators
    context = build_trace_context(trace, spans)

    # Load evaluator rows ordered by ord
    evaluator_rows: list[EvaluatorRow] = (
        db.query(EvaluatorRow)
        .filter(EvaluatorRow.rubric_version_id == rubric_ver.id, EvaluatorRow.enabled == True)  # noqa: E712
        .order_by(EvaluatorRow.ord)
        .all()
    )

    parsed_spec: dict = rubric_ver.parsed_spec or {}
    aggregate_method: str = parsed_spec.get("aggregate", "weighted_mean")
    fail_fast_global: bool = parsed_spec.get("fail_fast", False)
    auto_fail_conditions: list[dict] = parsed_spec.get("automatic_fail_conditions", [])

    score_records: list[EvaluationScore] = []
    any_succeeded = False
    all_failed = True
    total_cost = 0.0
    should_break = False

    for ev_row in evaluator_rows:
        if should_break:
            break

        # Budget guard for llm_judge
        if ev_row.type == "llm_judge":
            if not _check_judge_budget(trace.project_id, db):
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
                db.add(err_score)
                score_records.append(err_score)
                continue

        try:
            run_fn = REGISTRY[ev_row.type]
            result: EvaluatorResult = run_fn(context, ev_row.config)
            result = _sanitize_evaluator_result(result, ev_row.type)
            any_succeeded = True
            all_failed = False
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
        db.add(score_rec)
        score_records.append(score_rec)
        total_cost += result.cost_usd

        if result.score > 0 or result.passed:
            all_failed = False

        # fail_fast logic
        if (ev_row.fail_fast or fail_fast_global) and not result.passed:
            should_break = True

    # Aggregate scores (only successful, enabled scores — skip error-only)
    scoreable = [(float(sr.score), ev_row.weight) for sr, ev_row in zip(score_records, evaluator_rows) if sr is not None]
    # Rebuild properly — evaluator_rows and score_records may differ if budget abort skipped
    weight_map = {er.slug: er.weight for er in evaluator_rows}
    agg_pairs = [
        (float(sr.score), weight_map.get(sr.evaluator_slug, 1.0))
        for sr in score_records
        if sr.raw_output and "error" not in sr.raw_output or sr.passed
    ]
    # Simpler: include all scores in aggregation (including errors as 0)
    agg_pairs = [
        (float(sr.score), weight_map.get(sr.evaluator_slug, 1.0))
        for sr in score_records
    ]
    aggregate_score = _aggregate(agg_pairs, aggregate_method)
    threshold = float(parsed_spec.get("threshold", 0.7))

    # Check automatic_fail_conditions
    score_by_slug = {sr.evaluator_slug: sr for sr in score_records}
    auto_failed = False
    for cond in auto_fail_conditions:
        ev_id = cond.get("evaluator_id")
        if ev_id and ev_id in score_by_slug:
            if not score_by_slug[ev_id].passed:
                auto_failed = True
                break

    passed = (aggregate_score >= threshold) and not auto_failed

    # Determine final status
    if not score_records:
        status = "error"
        run.error_json = {"code": "no_evaluators_ran"}
    elif all(
        (sr.raw_output or {}).get("error") and not sr.passed
        for sr in score_records
    ):
        status = "error"
        run.error_json = {"code": "all_evaluators_failed"}
    else:
        status = "completed"
        if any((sr.raw_output or {}).get("error") for sr in score_records):
            run.run_metadata["partial_failure"] = True

    run.status = status
    run.aggregate_score = aggregate_score
    run.passed = passed if status == "completed" else None
    run.cost_usd = total_cost
    run.completed_at = _utcnow()
    run.latency_ms = int((time.monotonic() - run_start) * 1000)

    db.add(run)
    db.flush()
    return run
