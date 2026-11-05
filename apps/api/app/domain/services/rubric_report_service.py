"""Results of one rubric over time: what changed between versions, days and evaluators."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Query, Session, selectinload

from app.models import EvaluationRun, Rubric, Trace, utcnow

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30), "90d": timedelta(days=90)}


def filtered_traces(
    db: Session,
    project_id: str,
    *,
    environment: str | None = None,
    batch: str | None = None,
    name_contains: str | None = None,
    since: datetime | None = None,
) -> Query:
    query = db.query(Trace).filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
    if environment:
        query = query.filter(Trace.environment == environment)
    if batch:
        query = query.filter(Trace.metadata_json["batch"].as_string() == batch)
    if name_contains:
        query = query.filter(Trace.name.ilike(f"%{name_contains}%"))
    if since:
        query = query.filter(Trace.created_at >= since)
    return query


def _summary(runs: list[EvaluationRun]) -> dict:
    passed = sum(1 for run in runs if run.passed is True)
    failed = sum(1 for run in runs if run.passed is False)
    errors = sum(1 for run in runs if run.status == "error")
    # Partial runs have a score over part of the evidence: they are counted, not averaged.
    scores = [float(run.aggregate_score) for run in runs if run.passed is not None and run.aggregate_score is not None]
    return {
        "runs": len(runs),
        "passed": passed,
        "failed": failed,
        "unknown": len(runs) - passed - failed - errors,
        "errors": errors,
        "pass_rate": round(passed / (passed + failed), 4) if passed + failed else None,
        "avg_score": round(statistics.fmean(scores), 4) if scores else None,
        "score_stddev": round(statistics.pstdev(scores), 4) if len(scores) > 1 else None,
        "cost_usd": round(sum(float(run.cost_usd or 0) for run in runs), 6),
    }


def _by_evaluator(runs: list[EvaluationRun]) -> list[dict]:
    groups: dict[tuple[int, str], list] = defaultdict(list)
    for run in runs:
        for score in run.scores:
            groups[(run.rubric_version, score.evaluator_slug)].append(score)
    rows = []
    for (version, slug), scores in sorted(groups.items()):
        usable = [score for score in scores if not (score.raw_output or {}).get("error")]
        spreads = [float(score.raw_output["stddev"]) for score in usable if "stddev" in (score.raw_output or {})]
        rows.append(
            {
                "rubric_version": version,
                "evaluator": slug,
                "runs": len(scores),
                "errors": len(scores) - len(usable),
                "pass_rate": round(sum(1 for score in usable if score.passed) / len(usable), 4) if usable else None,
                "avg_score": round(statistics.fmean(float(score.score) for score in usable), 4) if usable else None,
                "avg_judge_stddev": round(statistics.fmean(spreads), 4) if spreads else None,
            }
        )
    return rows


def rubric_report(
    db: Session,
    rubric: Rubric,
    *,
    window: str,
    environment: str | None = None,
    batch: str | None = None,
) -> dict:
    traces = filtered_traces(
        db, rubric.project_id, environment=environment, batch=batch, since=utcnow() - WINDOWS[window]
    )
    runs = (
        db.query(EvaluationRun)
        .options(selectinload(EvaluationRun.scores))
        .filter(EvaluationRun.rubric_id == rubric.id, EvaluationRun.trace_id.in_(traces.with_entities(Trace.id)))
        .all()
    )
    created_at = dict(
        db.query(Trace.id, Trace.created_at).filter(Trace.id.in_({run.trace_id for run in runs})).all()
    ) if runs else {}

    by_version: dict[int, list[EvaluationRun]] = defaultdict(list)
    by_day: dict[tuple[str, int], list[EvaluationRun]] = defaultdict(list)
    for run in runs:
        by_version[run.rubric_version].append(run)
        by_day[(created_at[run.trace_id].date().isoformat(), run.rubric_version)].append(run)

    return {
        "rubric_id": rubric.id,
        "rubric_slug": rubric.slug,
        "window": window,
        "environment": environment,
        "batch": batch,
        "trace_count": traces.count(),
        "totals": _summary(runs),
        "by_version": [{"rubric_version": version, **_summary(by_version[version])} for version in sorted(by_version)],
        "by_day": [
            {"day": day, "rubric_version": version, **_summary(by_day[(day, version)])}
            for day, version in sorted(by_day)
        ],
        "by_evaluator": _by_evaluator(runs),
    }
