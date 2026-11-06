"""Read-only project quality policies over existing trace/eval evidence."""
from collections import defaultdict
from datetime import timezone
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.rubrics.outcomes import automatic_fail_flags, automatic_failures, raised_flags
from app.domain.services.analytics_service import p95_nearest_rank, resolve_overview_cutoff
from app.domain.services.rag_service import consolidate_rag, rag_filter_predicate
from app.models import EvaluationRun, QualityGateConfig, RubricVersion, Span, Trace, utcnow
from app.schemas import QualityGateConfigOut, QualityGateReason, QualityGateSettings


def get_config(db: Session, project_id: str) -> QualityGateConfigOut:
    config = db.get(QualityGateConfig, project_id)
    if config:
        return QualityGateConfigOut(
            **QualityGateSettings.model_validate(config, from_attributes=True).model_dump(),
            project_id=project_id, configured=True,
            updated_at=config.updated_at.replace(tzinfo=timezone.utc) if config.updated_at.tzinfo is None else config.updated_at,
        )
    return QualityGateConfigOut(project_id=project_id, configured=False)


def _usable_score(score) -> bool:
    return not any((score.raw_output or {}).get(key) for key in ("error", "parse_error", "schema_error"))


def calculate_status(db: Session, project_id: str, window: str, environment: str | None) -> dict:
    config = get_config(db, project_id)
    cutoff, _ = resolve_overview_cutoff(window, 7)
    traces_query = db.query(Trace).filter(
        Trace.project_id == project_id, Trace.deleted_at.is_(None), Trace.created_at >= cutoff,
    )
    if environment:
        traces_query = traces_query.filter(Trace.environment == environment)
    traces = traces_query.all()
    trace_ids = traces_query.with_entities(Trace.id).subquery()

    # Latest attempt per trace/rubric, including running/error attempts: an old
    # successful run must never conceal missing current evidence.
    ranked = select(
        EvaluationRun.id,
        func.row_number().over(
            partition_by=(EvaluationRun.trace_id, EvaluationRun.rubric_id),
            order_by=(EvaluationRun.created_at.desc(), EvaluationRun.id.desc()),
        ).label("rn"),
    ).where(
        EvaluationRun.project_id == project_id,
        EvaluationRun.trace_id.in_(select(trace_ids.c.id)),
    ).subquery()
    runs = db.query(EvaluationRun).options(selectinload(EvaluationRun.scores)).filter(
        EvaluationRun.id.in_(select(ranked.c.id).where(ranked.c.rn == 1)),
    ).all()
    versions = db.query(RubricVersion).filter(
        RubricVersion.rubric_id.in_({run.rubric_id for run in runs}),
    ).all() if runs else []
    specs = {(version.rubric_id, version.version): version.parsed_spec for version in versions}
    by_trace = defaultdict(list)
    for run in runs:
        by_trace[run.trace_id].append(run)

    scores = []
    critical_checked = 0
    critical_violations = 0
    for trace in traces:
        trace_runs = by_trace[trace.id]
        complete = [run for run in trace_runs if (
            run.status == "completed" and run.aggregate_score is not None
            and math.isfinite(float(run.aggregate_score))
            and 0 <= float(run.aggregate_score) <= 1
            and not (run.run_metadata or {}).get("partial_failure")
            and bool(run.scores) and all(_usable_score(score) for score in run.scores)
        )]
        if complete and len(complete) == len(trace_runs):
            # Equal trace weighting; repeated evaluations do not inflate quality.
            scores.append(sum(float(run.aggregate_score) for run in complete) / len(complete))

        has_rules = False
        rules_complete = bool(trace_runs) and len(complete) == len(trace_runs)
        violated = False
        for run in trace_runs:
            spec = specs.get((run.rubric_id, run.rubric_version))
            if spec is None:
                rules_complete = False
                continue
            conditions = spec.get("automatic_fail_conditions", [])
            executable = [condition for condition in conditions if condition.get("evaluator_id")]
            flags = automatic_fail_flags(spec)
            has_rules = has_rules or bool(executable) or bool(flags)
            valid_scores = [score for score in run.scores if _usable_score(score)] if run.status == "completed" else []
            score_slugs = {score.evaluator_slug for score in valid_scores}
            if any(condition["evaluator_id"] not in score_slugs for condition in executable):
                rules_complete = False
            # A judge that omitted "flags" reported nothing: that is missing evidence, not a clean result.
            if flags and not any(isinstance((score.raw_output or {}).get("flags"), list) for score in valid_scores):
                rules_complete = False
            violated = violated or bool(automatic_failures(valid_scores, executable)) or bool(raised_flags(valid_scores) & flags)
        critical_checked += int(has_rules and rules_complete)
        critical_violations += int(violated)

    rag_traces = traces_query.filter(rag_filter_predicate()).all()
    rag_ids = traces_query.filter(rag_filter_predicate()).with_entities(Trace.id).subquery()
    spans_by_trace = defaultdict(list)
    for span in db.query(Span).filter(Span.trace_id.in_(select(rag_ids.c.id))).order_by(Span.started_at.asc()).all():
        spans_by_trace[span.trace_id].append(span)
    ungrounded_rates = []
    for trace in rag_traces:
        rag = consolidate_rag(trace, spans_by_trace[trace.id])
        grounded, ungrounded = rag["grounded_claims"], rag["ungrounded_claims"]
        if grounded is not None and ungrounded is not None and grounded + ungrounded > 0:
            ungrounded_rates.append(ungrounded / (grounded + ungrounded))
        elif rag["support_rate"] is not None and 0 <= rag["support_rate"] <= 1:
            ungrounded_rates.append(1 - rag["support_rate"])

    n = len(traces)
    metrics = {
        "trace_count": n,
        "evaluated_trace_count": len(scores),
        "rag_trace_count": len(rag_traces),
        "grounding_trace_count": len(ungrounded_rates),
        "critical_checked_trace_count": critical_checked,
        "avg_score": sum(scores) / len(scores) if scores else None,
        "ungrounded_rate": sum(ungrounded_rates) / len(ungrounded_rates) if ungrounded_rates else None,
        "avg_cost_usd": sum(float(trace.total_cost_usd) for trace in traces) / n if n else None,
        "latency_p95_ms": int(p95_nearest_rank([trace.duration_ms for trace in traces])) if n else None,
        "critical_violations": critical_violations if critical_checked or critical_violations else None,
    }
    reasons = []
    if not config.configured:
        reasons.append(QualityGateReason(metric="configuration", status="review", code="not_configured", observed=None, threshold=None, sample_count=0))

    def check(metric, value, threshold, samples, expected, *, minimum=False, applicable=True):
        if not config.configured:
            state, code = "review", "not_configured"
        elif not applicable:
            state, code = "pass", "not_applicable"
        elif value is None:
            state, code = "review", "missing_evidence"
        elif (value < threshold if minimum else value > threshold):
            state, code = "fail", "threshold_exceeded"
        elif samples < expected:
            state, code = "review", "incomplete_evidence"
        else:
            state, code = "pass", "within_threshold"
        reasons.append(QualityGateReason(metric=metric, status=state, code=code, observed=value, threshold=threshold, sample_count=samples))

    check("quality", metrics["avg_score"], config.min_score, len(scores), n, minimum=True)
    check("ungrounded", metrics["ungrounded_rate"], config.max_ungrounded_rate, len(ungrounded_rates), len(rag_traces), applicable=bool(rag_traces) or not n)
    check("avg_cost", metrics["avg_cost_usd"], config.max_avg_cost_usd, n, n)
    check("p95", metrics["latency_p95_ms"], config.max_p95_ms, n, n)
    check("critical", metrics["critical_violations"], 0, critical_checked, n, applicable=config.require_zero_critical)
    state = "fail" if any(reason.status == "fail" for reason in reasons) else "review" if any(reason.status == "review" for reason in reasons) else "pass"
    return {
        "project_id": project_id, "status": state, "window": window, "environment": environment,
        "calculated_at": utcnow(), "config": config, "metrics": metrics, "reasons": reasons,
    }
