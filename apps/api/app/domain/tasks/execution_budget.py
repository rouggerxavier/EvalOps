"""Ledger and quota accounts in exact int64 units of 10^-8 USD.

Lock order on every path: project -> organization -> identity rows (user/membership/key).
"""
from decimal import Decimal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import func

from app import models as m
from app.domain.services.usage_service import current_period
from app.domain.tasks import service as s
from app.domain.tasks.contracts import Contract, digest
from app.domain.tasks.executions import Money
from app.security import new_id

USD_QUANTUM = Decimal("0.00000001")


class OrganizationBudget(Contract):
    enabled: bool = Field(default=False, strict=True)
    monthly_budget_usd: Money = Decimal("0")
    max_parallel: int = Field(default=1, ge=1, le=100, strict=True)


def units(amount):
    if isinstance(amount, bool):
        raise ValueError("invalid_usd_amount")
    value = Decimal(amount)
    if not value.is_finite() or value < 0 or value > Decimal("1000000000") or value != value.quantize(USD_QUANTUM):
        raise ValueError("invalid_usd_amount")
    return int(value / USD_QUANTUM)


def usd(value):
    return (Decimal(value) * USD_QUANTUM).quantize(USD_QUANTUM)


def lock_project(db, project_id):
    db.query(m.Project).filter_by(id=project_id).update({m.Project.name: m.Project.name}, synchronize_session=False)


def lock_organization(db, organization_id):
    db.query(m.Organization).filter_by(id=organization_id).update({m.Organization.name: m.Organization.name}, synchronize_session=False)


def current_budget(db, organization_id):
    return db.query(m.OrganizationExecutionBudgetRevision).filter_by(organization_id=organization_id).order_by(m.OrganizationExecutionBudgetRevision.version.desc()).first()


def serialize_budget(row, organization_id):
    return {"organization_id": organization_id, "version": row.version if row else 0,
            "budget": row.content if row else OrganizationBudget().model_dump(mode="json"), "content_hash": row.content_hash if row else None}


def update_budget(db, actor, project_id, payload, expected):
    project = s.project_access(db, actor, project_id, "admin")
    lock_organization(db, project.organization_id)
    owner = db.query(m.Membership).filter_by(user_id=actor.user_id, organization_id=project.organization_id).populate_existing().with_for_update().one_or_none()
    if owner is None or owner.role != "owner":
        raise HTTPException(403, "forbidden")
    current = current_budget(db, project.organization_id)
    if expected != (current.version if current else 0):
        raise HTTPException(409, "organization_budget_revision_conflict")
    account = db.get(m.OrganizationExecutionAccount, (project.organization_id, current_period()))
    if account:
        db.refresh(account)
    if account and units(payload.monthly_budget_usd) < account.reserved_units + account.spent_units:
        raise HTTPException(409, "budget_below_existing_commitments")
    content = payload.model_dump(mode="json")
    row = m.OrganizationExecutionBudgetRevision(id=new_id("orgbudget"), organization_id=project.organization_id,
        version=expected+1, content=content, content_hash=digest(content), created_by=actor.user_id)
    db.add(row)
    s.audit(db, actor, project_id, "execution.organization_budget.updated", f"orgbudget:{row.id}")
    return serialize_budget(row, project.organization_id)


def accounts(db, project, period):
    db.flush()
    organization = db.get(m.OrganizationExecutionAccount, (project.organization_id, period))
    local = db.get(m.ProjectExecutionAccount, (project.id, period))
    if organization is not None:
        db.refresh(organization)
    if local is not None:
        db.refresh(local)
    if organization is None:
        organization = m.OrganizationExecutionAccount(organization_id=project.organization_id, period=period, reserved_units=0, spent_units=0)
        db.add(organization)
    if local is None:
        local = m.ProjectExecutionAccount(project_id=project.id, period=period, reserved_units=0, spent_units=0)
        db.add(local)
    db.flush()
    return organization, local


def append(db, reservation, *, kind, event_key, amount, actor_id, measurement_source, attempt_id=None, pricing_version="execution-budget@1"):
    row = m.ExecutionLedgerEntry(id=new_id("ledger"), execution_id=reservation.execution_id, project_id=reservation.project_id,
        organization_id=reservation.organization_id, period=reservation.period, kind=kind, event_key=event_key,
        amount_units=units(amount), actor_id=actor_id, measurement_source=measurement_source, attempt_id=attempt_id, pricing_version=pricing_version)
    db.add(row)
    return row


def active_slots(db, **filters):
    return db.query(func.coalesce(func.sum(m.ExecutionReservation.slots), 0)).filter_by(active=True, **filters).scalar()


def reserve(db, actor, execution, *, policy_revision_id, organization_budget_revision_id, amount, slots):
    """Caller holds the project write lock; ledger/counters are committed with execution."""
    lock_project(db, execution.project_id)
    project = s.project_access(db, actor, execution.project_id, "evaluate")
    lock_organization(db, project.organization_id)
    if execution.origin != "controlled_runner" or execution.status != "queued":
        raise HTTPException(409, "execution_is_not_reservable")
    current = current_budget(db, project.organization_id)
    project_revision = db.query(m.ExecutionPolicyRevision).filter_by(project_id=project.id).order_by(m.ExecutionPolicyRevision.version.desc()).first()
    if current is None or current.id != organization_budget_revision_id or project_revision is None or project_revision.id != policy_revision_id:
        raise HTTPException(409, "execution_plan_policy_changed")
    from app.domain.tasks.runner_control import ExecutionPolicy
    organization_policy = OrganizationBudget.model_validate(current.content)
    policy = ExecutionPolicy.model_validate(project_revision.content)
    if not policy.enabled or not organization_policy.enabled:
        raise HTTPException(403, "execution_policy_disabled")
    if type(slots) is not int or not 1 <= slots <= 100 or Decimal(amount) > policy.max_cost_per_run_usd:
        raise HTTPException(422, "execution_limit_exceeds_policy")
    count = units(amount)
    period = current_period()
    organization, local = accounts(db, project, period)
    if (organization.reserved_units + organization.spent_units + count > units(organization_policy.monthly_budget_usd)
            or local.reserved_units + local.spent_units + count > units(policy.monthly_budget_usd)):
        raise HTTPException(402, "execution_budget_exceeded")
    if (active_slots(db, organization_id=project.organization_id) + slots > organization_policy.max_parallel
            or active_slots(db, project_id=project.id) + slots > policy.max_parallel):
        raise HTTPException(429, "execution_parallel_limit")
    reservation = m.ExecutionReservation(execution_id=execution.id, project_id=project.id, organization_id=project.organization_id,
        period=period, reserved_units=count, spent_units=None, slots=slots, active=True, state="reserved")
    db.add(reservation)
    organization.reserved_units += count
    local.reserved_units += count
    append(db, reservation, kind="reserve", event_key="reserve", amount=amount, actor_id=actor.id, measurement_source="sealed_manifest_limit")
    return reservation


def settle(db, reservation, *, amount, actor_id, attempt_id=None, measurement_source, pricing_version):
    """Known cost releases the hold; callers must prove completion/isolation before releasing slots."""
    lock_project(db, reservation.project_id)
    db.refresh(reservation)
    if reservation.state == "settled":
        if reservation.spent_units != units(amount):
            raise HTTPException(409, "execution_settlement_conflict")
        return
    project = db.get(m.Project, reservation.project_id)
    lock_organization(db, reservation.organization_id)
    organization, local = accounts(db, project, reservation.period)
    cost = units(amount)
    for account in (organization, local):
        account.reserved_units -= reservation.reserved_units
        account.spent_units += cost
    append(db, reservation, kind="settle", event_key="settle", amount=amount, actor_id=actor_id,
           attempt_id=attempt_id, measurement_source=measurement_source, pricing_version=pricing_version)
    append(db, reservation, kind="release", event_key="release", amount=usd(reservation.reserved_units), actor_id=actor_id,
           attempt_id=attempt_id, measurement_source="settled_hold_release")
    reservation.state = "settled"
    reservation.spent_units = cost
    reservation.settled_at = m.utcnow()
