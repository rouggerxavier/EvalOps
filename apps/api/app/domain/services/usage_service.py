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


def get_or_create_counter(db: Session, org_id: str, period: str) -> UsageCounter:
    row = (
        db.query(UsageCounter)
        .filter(UsageCounter.organization_id == org_id, UsageCounter.period == period)
        .one_or_none()
    )
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
    )
    db.add(row)
    db.flush()
    return row


def enforce_quota(db: Session, project: Project, field: str, increment: int = 1) -> None:
    sub = ensure_subscription(db, project.organization_id)
    period = current_period()
    counter = get_or_create_counter(db, project.organization_id, period)
    plan = db.get(Plan, sub.plan_id)
    if not plan:
        return
    limit_by_field = {
        "traces_ingested": int(plan.monthly_trace_limit),
        "evaluations_run": int(plan.monthly_eval_limit),
        "exports_created": int(plan.monthly_export_limit),
    }
    if field not in limit_by_field:
        return
    current_value = int(getattr(counter, field) or 0)
    if current_value + increment > limit_by_field[field]:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="quota_exceeded")


def increment_usage(
    db: Session,
    org_id: str,
    *,
    traces: int = 0,
    evals: int = 0,
    exports: int = 0,
    cost_usd: float = 0.0,
) -> UsageCounter:
    row = get_or_create_counter(db, org_id, current_period())
    row.traces_ingested = int(row.traces_ingested or 0) + max(0, traces)
    row.evaluations_run = int(row.evaluations_run or 0) + max(0, evals)
    row.exports_created = int(row.exports_created or 0) + max(0, exports)
    row.cost_usd = float(Decimal(str(row.cost_usd or 0)) + Decimal(str(max(0.0, cost_usd))))
    db.add(row)
    return row
