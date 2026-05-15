from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Plan, Project, Subscription, UsageCounter
from app.security import new_id


def current_period(now: datetime | None = None) -> str:
    ref = now or datetime.now(timezone.utc)
    return f"{ref.year:04d}-{ref.month:02d}"


def ensure_subscription(db: Session, org_id: str) -> Subscription:
    sub = db.query(Subscription).filter(Subscription.organization_id == org_id).one_or_none()
    if sub:
        return sub
    plan = db.query(Plan).filter(Plan.code == "free").one_or_none()
    if not plan:
        plan = Plan(
            id=new_id("pln"),
            code="free",
            name="Free",
            monthly_trace_limit=1000,
            monthly_eval_limit=500,
            monthly_export_limit=10,
            monthly_span_limit=50_000,
            monthly_token_limit=5_000_000,
            monthly_judge_budget_usd=20,
        )
        db.add(plan)
        db.flush()
    sub = Subscription(
        id=new_id("sub"),
        organization_id=org_id,
        plan_id=plan.id,
        status="active",
    )
    db.add(sub)
    db.flush()
    return sub


def _is_postgres(db: Session) -> bool:
    try:
        return db.bind.dialect.name == "postgresql"  # type: ignore[union-attr]
    except Exception:
        return False


def get_or_create_counter(db: Session, org_id: str, period: str, *, lock: bool = False) -> UsageCounter:
    """Fetch (or create) the monthly counter row.

    G-20: when ``lock=True`` and dialect is Postgres, the existing row is fetched
    with ``SELECT ... FOR UPDATE`` (pessimistic lock) so concurrent ingest/eval/
    export workers serialize their increment-and-commit. SQLite ignores the
    locking clause silently — concurrency in SQLite remains at file-lock level
    (writes already serialize via SQLite's internal lock).
    """
    query = db.query(UsageCounter).filter(
        UsageCounter.organization_id == org_id, UsageCounter.period == period
    )
    if lock and _is_postgres(db):
        query = query.with_for_update()
    row = query.one_or_none()
    if row:
        return row
    row = UsageCounter(
        id=new_id("usc"),
        organization_id=org_id,
        period=period,
        traces_ingested=0,
        evaluations_run=0,
        exports_created=0,
        cost_usd=0,
        spans_ingested=0,
        tokens_ingested=0,
    )
    db.add(row)
    db.flush()
    return row


def _plan_limit(plan: Plan, field: str) -> int | None:
    """Return the integer limit for ``field`` from the plan, or None if not gated."""
    mapping = {
        "traces_ingested": int(plan.monthly_trace_limit or 0),
        "evaluations_run": int(plan.monthly_eval_limit or 0),
        "exports_created": int(plan.monthly_export_limit or 0),
        "spans_ingested": int(plan.monthly_span_limit or 0),
        "tokens_ingested": int(plan.monthly_token_limit or 0),
    }
    return mapping.get(field)


def enforce_quota(db: Session, project: Project, field: str, increment: int = 1) -> None:
    """Raise 402 if the increment would exceed the plan's monthly limit for ``field``.

    Supports G-07 fields: ``spans_ingested`` and ``tokens_ingested`` in addition
    to traces/evaluations/exports.
    """
    sub = ensure_subscription(db, project.organization_id)
    period = current_period()
    counter = get_or_create_counter(db, project.organization_id, period)
    plan = db.get(Plan, sub.plan_id)
    if not plan:
        return
    limit = _plan_limit(plan, field)
    if limit is None:
        return
    current_value = int(getattr(counter, field) or 0)
    if current_value + max(0, increment) > limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={"error": "quota_exceeded", "field": field, "limit": limit},
        )


def increment_usage(
    db: Session,
    org_id: str,
    *,
    traces: int = 0,
    evals: int = 0,
    exports: int = 0,
    cost_usd: float = 0.0,
    spans: int = 0,
    tokens: int = 0,
) -> UsageCounter:
    """Increment the monthly counters for an org.

    G-20: takes a pessimistic lock on the existing row when running on Postgres
    so concurrent writers do not race read-modify-write. On SQLite the lock is a
    no-op but file-level write serialisation already prevents lost updates for
    single-process ingest.
    """
    row = get_or_create_counter(db, org_id, current_period(), lock=True)
    row.traces_ingested = int(row.traces_ingested or 0) + max(0, traces)
    row.evaluations_run = int(row.evaluations_run or 0) + max(0, evals)
    row.exports_created = int(row.exports_created or 0) + max(0, exports)
    row.spans_ingested = int(row.spans_ingested or 0) + max(0, spans)
    row.tokens_ingested = int(row.tokens_ingested or 0) + max(0, tokens)
    row.cost_usd = float(Decimal(str(row.cost_usd or 0)) + Decimal(str(max(0.0, cost_usd))))
    db.add(row)
    return row


def judge_budget_for_org(db: Session, org_id: str) -> float:
    """G-12: return the plan's monthly judge budget in USD.

    Falls back to the legacy default (20 USD) when the org has no subscription
    or when the plan column is missing/zero.
    """
    sub = db.query(Subscription).filter(Subscription.organization_id == org_id).one_or_none()
    if sub is None:
        return 20.0
    plan = db.get(Plan, sub.plan_id)
    if plan is None:
        return 20.0
    raw = getattr(plan, "monthly_judge_budget_usd", None)
    if raw is None:
        return 20.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 20.0
    return value if value > 0 else 20.0
