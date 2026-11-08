from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from app.models import Notification, Plan, Project, Subscription, UsageCounter
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


def _counter_query(db: Session, org_id: str, period: str, *, lock: bool) -> Query[UsageCounter]:
    query = db.query(UsageCounter).filter(
        UsageCounter.organization_id == org_id,
        UsageCounter.period == period,
    )
    if lock and _is_postgres(db):
        # Refresh preflight reads after waiting, preserving this transaction's pending increments.
        for row in list(db.dirty):
            if isinstance(row, UsageCounter) and row.organization_id == org_id and row.period == period:
                db.flush([row])
        query = query.with_for_update().populate_existing()
    return query


def _quota_exceeded(field: str, limit: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={"error": "quota_exceeded", "field": field, "limit": limit},
    )


def _usage_deltas(
    *,
    traces: int = 0,
    evals: int = 0,
    exports: int = 0,
    spans: int = 0,
    tokens: int = 0,
) -> dict[str, int]:
    return {
        "traces_ingested": max(0, traces),
        "evaluations_run": max(0, evals),
        "exports_created": max(0, exports),
        "spans_ingested": max(0, spans),
        "tokens_ingested": max(0, tokens),
    }


def _apply_counter_deltas(
    row: UsageCounter,
    *,
    traces: int = 0,
    evals: int = 0,
    exports: int = 0,
    cost_usd: float = 0.0,
    spans: int = 0,
    tokens: int = 0,
) -> None:
    row.traces_ingested = int(row.traces_ingested or 0) + max(0, traces)
    row.evaluations_run = int(row.evaluations_run or 0) + max(0, evals)
    row.exports_created = int(row.exports_created or 0) + max(0, exports)
    row.spans_ingested = int(row.spans_ingested or 0) + max(0, spans)
    row.tokens_ingested = int(row.tokens_ingested or 0) + max(0, tokens)
    row.cost_usd = float(Decimal(str(row.cost_usd or 0)) + Decimal(str(max(0.0, cost_usd))))


def get_or_create_counter(db: Session, org_id: str, period: str, *, lock: bool = False) -> UsageCounter:
    """Fetch (or create) the monthly counter row.

    G-20: when ``lock=True`` and dialect is Postgres, the existing row is fetched
    with ``SELECT ... FOR UPDATE`` (pessimistic lock) so concurrent ingest/eval/
    export workers serialize their increment-and-commit. SQLite ignores the
    locking clause silently — concurrency in SQLite remains at file-lock level
    (writes already serialize via SQLite's internal lock).
    """
    row = _counter_query(db, org_id, period, lock=lock).one_or_none()
    if row:
        return row

    candidate = UsageCounter(
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
    try:
        # Savepoint rollback protects the caller's outer transaction state.
        with db.begin_nested():
            db.add(candidate)
            db.flush()
        return candidate
    except IntegrityError:
        # Concurrent insert for (organization_id, period): reload the winner.
        existing = _counter_query(db, org_id, period, lock=lock).one_or_none()
        if existing is not None:
            return existing
        raise


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


def _notify_quota_threshold(db: Session, counter: UsageCounter, field: str, limit: int, previous: int) -> None:
    """Warn once at 80%, in the usage transaction, including jumps to exhaustion.

    Copies belong to the org's currently active projects, with independent read
    state. Projects created later wait for the next crossing/month. Judge spend
    is excluded: the usage cost counter also includes non-judge ingestion cost.
    """
    used = int(getattr(counter, field) or 0)
    if limit <= 0 or previous * 100 >= limit * 80 or used * 100 < limit * 80:
        return
    labels = {
        "traces_ingested": "traces",
        "evaluations_run": "avaliações",
        "exports_created": "exportações",
        "spans_ingested": "spans",
        "tokens_ingested": "tokens",
    }
    projects = db.query(Project.id).filter(
        Project.organization_id == counter.organization_id,
        Project.archived_at.is_(None),
    ).all()
    for (project_id,) in projects:
        key = f"{counter.organization_id}:{counter.period}:{field}:80:{project_id}"
        notification_id = "ntf_" + sha256(key.encode()).hexdigest()[:60]
        if db.get(Notification, notification_id) is not None or any(
            isinstance(row, Notification) and row.id == notification_id for row in db.new
        ):
            continue
        db.add(Notification(
            id=notification_id,
            project_id=project_id,
            kind="warn",
            title=f"Cota da organização: {labels[field]} em 80% ou mais ({used}/{limit})",
            meta={
                "scope": "organization",
                "organization_id": counter.organization_id,
                "period": counter.period,
                "resource": field,
                "threshold_percent": 80,
                "used": used,
                "limit": limit,
            },
        ))


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
        raise _quota_exceeded(field, limit)


def apply_usage_with_quota(
    db: Session,
    project: Project,
    *,
    traces: int = 0,
    evals: int = 0,
    exports: int = 0,
    cost_usd: float = 0.0,
    spans: int = 0,
    tokens: int = 0,
) -> UsageCounter:
    """Atomically enforce quota and apply usage deltas in the same transaction.

    The caller controls commit/rollback boundaries; this function only mutates
    the current DB transaction.
    """
    sub = ensure_subscription(db, project.organization_id)
    plan = db.get(Plan, sub.plan_id)
    counter = get_or_create_counter(db, project.organization_id, current_period(), lock=True)
    deltas = _usage_deltas(
        traces=traces,
        evals=evals,
        exports=exports,
        spans=spans,
        tokens=tokens,
    )
    previous = {field: int(getattr(counter, field) or 0) for field in deltas}
    if plan is not None:
        for field, delta in deltas.items():
            if delta <= 0:
                continue
            limit = _plan_limit(plan, field)
            if limit is None:
                continue
            current_value = int(getattr(counter, field) or 0)
            if current_value + delta > limit:
                raise _quota_exceeded(field, limit)

    _apply_counter_deltas(
        counter,
        traces=traces,
        evals=evals,
        exports=exports,
        cost_usd=cost_usd,
        spans=spans,
        tokens=tokens,
    )
    db.add(counter)
    if plan is not None:
        for field, delta in deltas.items():
            limit = _plan_limit(plan, field)
            if delta > 0 and limit is not None:
                _notify_quota_threshold(db, counter, field, limit, previous[field])
    return counter


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
    """Increment the monthly counters for an org without quota checks.

    G-20: takes a pessimistic lock on the existing row when running on Postgres
    so concurrent writers do not race read-modify-write. On SQLite the lock is a
    no-op but file-level write serialisation already prevents lost updates for
    single-process ingest.
    """
    row = get_or_create_counter(db, org_id, current_period(), lock=True)
    sub = ensure_subscription(db, org_id)
    plan = db.get(Plan, sub.plan_id)
    deltas = _usage_deltas(traces=traces, evals=evals, exports=exports, spans=spans, tokens=tokens)
    previous = {field: int(getattr(row, field) or 0) for field in deltas}
    _apply_counter_deltas(
        row,
        traces=traces,
        evals=evals,
        exports=exports,
        cost_usd=cost_usd,
        spans=spans,
        tokens=tokens,
    )
    db.add(row)
    if plan is not None:
        for field, delta in deltas.items():
            limit = _plan_limit(plan, field)
            if delta > 0 and limit is not None:
                _notify_quota_threshold(db, row, field, limit, previous[field])
    return row


def set_org_plan_limits(db: Session, org_id: str, **limits: float) -> Plan:
    """Move one org to its own plan with the given ``Plan`` limit columns.

    Plans are shared by every org on them, so the limits are never edited in
    place. Caller commits.
    """
    sub = ensure_subscription(db, org_id)
    code = f"org-{org_id}"
    plan = db.query(Plan).filter(Plan.code == code).one_or_none()
    if plan is None:
        current = db.get(Plan, sub.plan_id)
        plan = Plan(
            id=new_id("pln"),
            code=code,
            name=f"Custom {org_id}",
            monthly_trace_limit=current.monthly_trace_limit,
            monthly_eval_limit=current.monthly_eval_limit,
            monthly_export_limit=current.monthly_export_limit,
            monthly_span_limit=current.monthly_span_limit,
            monthly_token_limit=current.monthly_token_limit,
            monthly_judge_budget_usd=current.monthly_judge_budget_usd,
        )
        db.add(plan)
        db.flush()
    for column, value in limits.items():
        setattr(plan, column, value)
    sub.plan_id = plan.id
    db.add(sub)
    return plan


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
