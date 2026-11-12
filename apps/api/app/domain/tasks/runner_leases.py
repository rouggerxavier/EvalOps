"""Single lease per controlled execution; the API grants and closes leases but never runs code.

Lock order on every write path: project -> organization -> identity rows, matching execution_budget.
Uncertainty never schedules another attempt: a retry needs a new plan, admission and reservation.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import Field

from app import models as m
from app.domain.services.audit_service import record_audit
from app.domain.tasks import execution_budget as budget
from app.domain.tasks import execution_plans as plans
from app.domain.tasks import service as s
from app.domain.tasks.contracts import Contract, canonical_json, digest
from app.domain.tasks.executions import ExecutionManifest, ReportedCost
from app.domain.tasks.runner_control import ExecutionPolicy, authenticate_runner
from app.security import new_id
from app.timestamps import server_timestamp

LEASE_TTL_S = 60
HEARTBEAT_INTERVAL_S = 20
IDLE_RETRY_AFTER_S = 5
CLAIM_SCAN = 20
MAX_LATE_REPORTS = 20


class RunnerReport(Contract):
    status: Literal["succeeded", "failed", "timed_out", "cancelled", "uncertain"]
    exit_reason: str = Field(min_length=1, max_length=2000)
    capture_status: Literal["complete", "partial", "uncertain"]
    cost: ReportedCost


def token_digest(raw):
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def iso(value):
    return server_timestamp(value).isoformat() if value else None


def wall_time_deadline(claimed_at, execution):
    limit_s = ExecutionManifest.model_validate_json(execution.manifest_content).limits.wall_time_s
    return server_timestamp(claimed_at) + timedelta(seconds=limit_s)


def lease_expires_at(claimed_at, now, execution):
    return min(now + timedelta(seconds=LEASE_TTL_S), wall_time_deadline(claimed_at, execution))


def is_lease_expired(db, lease, now):
    if server_timestamp(lease.expires_at) <= now:
        return True
    execution = db.get(m.Execution, lease.execution_id)
    return wall_time_deadline(lease.claimed_at, execution) <= now


def fail_after_commit(db, status, detail):
    """Persist the state change that explains the refusal, then refuse."""
    db.commit()
    raise HTTPException(status, detail)


def runner_audit(db, project_id, action, execution_id, runner_id, **payload):
    project = db.get(m.Project, project_id)
    record_audit(db, action, organization_id=project.organization_id, target_type="execution", target_id=execution_id,
                 payload={"project_id": project_id, "runner_id": runner_id, **payload})


def runner_session(db, runner_id, raw):
    """Authenticate, take the project lock shared with disable/revoke, then authenticate again."""
    runner, _ = authenticate_runner(db, runner_id, raw)
    budget.lock_project(db, runner.project_id)
    db.expire_all()
    db.info.pop("task_sources", None)
    db.info.pop("task_dataset_projects", None)
    runner, credential = authenticate_runner(db, runner_id, raw)
    budget.lock_organization(db, db.get(m.Project, runner.project_id).organization_id)
    return runner, credential


def revalidate(db, execution):
    """Current sources, original identity, runner and current policy/budget; copied data is not trusted."""
    schedule = db.get(m.ExecutionSchedule, execution.id)
    plan = db.get(m.ExecutionPlan, schedule.plan_id)
    manifest = ExecutionManifest.model_validate_json(plan.manifest_content)
    actor = plans.original_actor(db, execution, schedule)
    policy_row, organization_row, _ = plans.approved(db, actor, execution.project_id, manifest, plan.runner_id)
    s.load(db, actor, "execution", execution.id, permission="evaluate")
    reservation = db.get(m.ExecutionReservation, execution.id)
    if (reservation is None or reservation.state != "reserved" or not reservation.active
            or reservation.reserved_units < budget.units(manifest.limits.max_cost_usd)
            or reservation.slots < manifest.limits.max_parallel):
        raise HTTPException(409, "execution_reservation_unavailable")
    project = db.get(m.Project, execution.project_id)
    organization_account = db.get(m.OrganizationExecutionAccount, (project.organization_id, reservation.period))
    local_account = db.get(m.ProjectExecutionAccount, (project.id, reservation.period))
    if (organization_account is None or local_account is None
            or organization_account.reserved_units < reservation.reserved_units
            or local_account.reserved_units < reservation.reserved_units):
        raise HTTPException(409, "execution_reservation_unavailable")
    policy = ExecutionPolicy.model_validate(policy_row.content)
    organization_policy = budget.OrganizationBudget.model_validate(organization_row.content)
    if (execution.status == "queued" or organization_row.id != plan.organization_budget_revision_id) and (
        organization_account.reserved_units + organization_account.spent_units > budget.units(organization_policy.monthly_budget_usd)
    ):
        raise HTTPException(402, "execution_budget_exceeded")
    if (execution.status == "queued" or policy_row.id != plan.policy_revision_id) and (
        local_account.reserved_units + local_account.spent_units > budget.units(policy.monthly_budget_usd)
    ):
        raise HTTPException(402, "execution_budget_exceeded")
    if (execution.status == "queued" or organization_row.id != plan.organization_budget_revision_id) and (
        budget.active_slots(db, organization_id=project.organization_id) > organization_policy.max_parallel
    ):
        raise HTTPException(429, "execution_parallel_limit")
    if (execution.status == "queued" or policy_row.id != plan.policy_revision_id) and (
        budget.active_slots(db, project_id=project.id) > policy.max_parallel
    ):
        raise HTTPException(429, "execution_parallel_limit")


def record_attempt(db, execution, lease, report, source, warnings=()):
    schedule = db.get(m.ExecutionSchedule, execution.id)
    content = {**report, "producer": "registered_runner", "runner_id": lease.runner_id, "terminal_source": source,
               "claimed_at": iso(lease.claimed_at), "ended_at": iso(lease.ended_at),
               "cancel_requested": schedule.cancel_requested_at is not None, "warnings": list(warnings), "decision": None}
    db.add(m.ExecutionAttempt(id=lease.attempt_id, execution_id=execution.id, project_id=execution.project_id,
        environment=execution.environment, attempt_number=1, result_content=canonical_json(content), result_hash=digest(content),
        access_label={**execution.access_label, "source_refs": [f"execution:{execution.id}"]}))


def close_uncertain(db, lease, state, reason, cost=None):
    """Work may have started: keep hold and slot on unknown cost, or settle provided cost once and free slot."""
    execution = db.get(m.Execution, lease.execution_id)
    lease.state, lease.ended_at = state, m.utcnow()
    execution.status = "uncertain"
    reservation = db.get(m.ExecutionReservation, lease.execution_id)
    warnings = []
    if cost is not None and cost.state == "provided" and reservation is not None and reservation.state == "reserved":
        if budget.units(cost.amount_usd) > reservation.reserved_units:
            warnings.append("reported_cost_exceeds_reserved_limit")
        budget.settle(db, reservation, amount=cost.amount_usd, actor_id=lease.runner_id, attempt_id=lease.attempt_id,
                      measurement_source=cost.measurement_source, pricing_version=cost.pricing_version or "runner-reported@1")
        reservation.active = False
        attempt_cost = cost.model_dump(mode="json")
    else:
        if reservation is not None:
            reservation.state = "unknown"
        attempt_cost = (cost.model_dump(mode="json") if cost is not None
                        else {"state": "unknown", "amount_usd": None, "measurement_source": None, "pricing_version": None})
    record_attempt(db, execution, lease, {"status": "uncertain", "exit_reason": reason, "capture_status": "uncertain",
                                          "cost": attempt_cost}, reason, warnings)
    runner_audit(db, lease.project_id, "execution.lease.lost", execution.id, lease.runner_id, reason=reason)
    db.flush()  # callers may refresh rows afterwards


def expire_lapsed(db, project_id):
    """Lazy sweep under the project lock. shortcut: no background sweeper, add one when status freshness matters."""
    now = m.utcnow()
    for lease in db.query(m.ExecutionLease).filter_by(project_id=project_id, state="active").all():
        if is_lease_expired(db, lease, now):
            close_uncertain(db, lease, "expired", "lease_expired")


def drop_runner_leases(db, project_id, reason, **filters):
    """Disable/revoke callers hold the project lock."""
    for lease in db.query(m.ExecutionLease).filter_by(project_id=project_id, state="active", **filters).all():
        close_uncertain(db, lease, "lost", reason)


def cancel_unstarted(db, execution, runner_id, reason):
    reservation = db.get(m.ExecutionReservation, execution.id)
    budget.settle(db, reservation, amount="0", actor_id=runner_id, measurement_source="server_cancelled_before_lease",
                  pricing_version="execution-budget@1")
    reservation.active = False
    execution.status = "cancelled"
    runner_audit(db, execution.project_id, "execution.cancelled.restricted", execution.id, runner_id, reason=str(reason))


def grant(lease, execution, token):
    manifest = ExecutionManifest.model_validate_json(execution.manifest_content)
    return {"execution_id": execution.id, "attempt_id": lease.attempt_id, "lease_token": token,
            "expires_at": iso(lease.expires_at), "lease_ttl_s": min(LEASE_TTL_S, manifest.limits.wall_time_s),
            "heartbeat_interval_s": HEARTBEAT_INTERVAL_S,
            "manifest_hash": execution.manifest_hash, "manifest": manifest.model_dump(mode="json")}


def idle():
    return {"lease": None, "retry_after_s": IDLE_RETRY_AFTER_S}


def has_claim_work(db, runner, claim_key):
    now = m.utcnow()
    if any(is_lease_expired(db, lease, now)
           for lease in db.query(m.ExecutionLease).filter_by(project_id=runner.project_id, state="active").all()):
        return True
    if db.query(m.ExecutionLease.execution_id).filter_by(runner_id=runner.id, claim_key=claim_key).first() is not None:
        return True
    return (db.query(m.Execution.id)
            .join(m.ExecutionSchedule, m.ExecutionSchedule.execution_id == m.Execution.id)
            .join(m.ExecutionPlan, m.ExecutionPlan.id == m.ExecutionSchedule.plan_id)
            .filter(m.ExecutionPlan.runner_id == runner.id, m.Execution.status == "queued")
            .first() is not None)


def claim(db, runner_id, raw_key, claim_key):
    if not raw_key:
        raise HTTPException(401, "unauthorized")
    if not claim_key or len(claim_key) > 128:
        raise HTTPException(422, "idempotency_key_required")
    runner, _ = authenticate_runner(db, runner_id, raw_key)
    if not has_claim_work(db, runner, claim_key):
        return idle()
    runner, credential = runner_session(db, runner_id, raw_key)
    expire_lapsed(db, runner.project_id)
    previous = db.query(m.ExecutionLease).filter_by(runner_id=runner.id, claim_key=claim_key).one_or_none()
    if previous is not None:
        # A lost response is replayed with a new token only while no heartbeat proves delivery and authorization holds.
        if previous.state != "active" or previous.heartbeat_at is not None or previous.credential_id != credential.id:
            fail_after_commit(db, 409, "execution_lease_already_delivered")
        execution = db.get(m.Execution, previous.execution_id)
        try:
            revalidate(db, execution)
        except HTTPException:
            close_uncertain(db, previous, "lost", "revalidation_failed")
            fail_after_commit(db, 409, "execution_lease_not_active")
        token = secrets.token_urlsafe(32)
        previous.token_hash = token_digest(token)
        return {"lease": grant(previous, execution, token)}
    queued = (db.query(m.Execution).join(m.ExecutionSchedule, m.ExecutionSchedule.execution_id == m.Execution.id)
              .join(m.ExecutionPlan, m.ExecutionPlan.id == m.ExecutionSchedule.plan_id)
              .filter(m.ExecutionPlan.runner_id == runner.id, m.Execution.status == "queued")
              .order_by(m.Execution.created_at, m.Execution.id).limit(CLAIM_SCAN).all())
    for execution in queued:
        try:
            revalidate(db, execution)
        except HTTPException as error:
            cancel_unstarted(db, execution, runner.id, error.detail)  # restriction cancels work that never started
            continue
        token = secrets.token_urlsafe(32)
        now = m.utcnow()
        lease = m.ExecutionLease(execution_id=execution.id, project_id=execution.project_id, attempt_id=new_id("attempt"),
            runner_id=runner.id, credential_id=credential.id, claim_key=claim_key, token_hash=token_digest(token),
            state="active", claimed_at=now, expires_at=lease_expires_at(now, now, execution))
        execution.status = "running"
        db.add(lease)
        db.flush()
        runner_audit(db, execution.project_id, "execution.lease.granted", execution.id, runner.id, attempt_id=lease.attempt_id)
        return {"lease": grant(lease, execution, token)}
    return idle()


def held_lease(db, execution_id, attempt_id, raw_key, raw_token):
    """Every failure before the token matches is an indistinguishable 401."""
    if not raw_key or not raw_token:
        raise HTTPException(401, "unauthorized")
    lease = db.get(m.ExecutionLease, execution_id)
    if lease is None or lease.attempt_id != attempt_id:
        raise HTTPException(401, "unauthorized")
    _, credential = runner_session(db, lease.runner_id, raw_key)
    db.refresh(lease)
    if credential.id != lease.credential_id or not hmac.compare_digest(lease.token_hash, token_digest(raw_token)):
        raise HTTPException(401, "unauthorized")
    expire_lapsed(db, lease.project_id)
    return lease


def heartbeat(db, execution_id, attempt_id, raw_key, raw_token):
    lease = held_lease(db, execution_id, attempt_id, raw_key, raw_token)
    if lease.state != "active":
        fail_after_commit(db, 409, "execution_lease_not_active")
    execution = db.get(m.Execution, execution_id)
    try:
        revalidate(db, execution)
    except HTTPException:
        close_uncertain(db, lease, "lost", "revalidation_failed")
        fail_after_commit(db, 409, "execution_lease_not_active")
    now = m.utcnow()
    expires_at = lease_expires_at(lease.claimed_at, now, execution)
    if expires_at <= now:
        close_uncertain(db, lease, "expired", "lease_expired")
        fail_after_commit(db, 409, "execution_lease_not_active")
    lease.heartbeat_at, lease.expires_at = now, expires_at
    schedule = db.get(m.ExecutionSchedule, execution_id)
    return {"execution_id": execution_id, "attempt_id": attempt_id, "expires_at": iso(lease.expires_at),
            "heartbeat_interval_s": HEARTBEAT_INTERVAL_S, "cancel_requested": schedule.cancel_requested_at is not None}


def keep_late(db, lease, report, reason):
    content = report.model_dump(mode="json")
    content_hash = digest(content)
    rows = db.query(m.ExecutionLateReport).filter_by(attempt_id=lease.attempt_id)
    if rows.filter_by(content_hash=content_hash).first() is None and rows.count() < MAX_LATE_REPORTS:
        db.add(m.ExecutionLateReport(id=new_id("latereport"), execution_id=lease.execution_id, project_id=lease.project_id,
            attempt_id=lease.attempt_id, reason=reason, content=canonical_json(content), content_hash=content_hash))
        runner_audit(db, lease.project_id, "execution.report.late", lease.execution_id, lease.runner_id, reason=reason)


def completion(lease, execution):
    return {"execution_id": execution.id, "attempt_id": lease.attempt_id, "status": execution.status}


def complete(db, execution_id, attempt_id, raw_key, raw_token, report):
    lease = held_lease(db, execution_id, attempt_id, raw_key, raw_token)
    execution = db.get(m.Execution, execution_id)
    report_hash = digest(report.model_dump(mode="json"))
    if lease.state != "active":
        if lease.state == "completed" and lease.report_hash == report_hash:
            return completion(lease, execution)
        keep_late(db, lease, report, "lease_closed")
        fail_after_commit(db, 409, "execution_already_terminal")
    try:
        revalidate(db, execution)
    except HTTPException:
        close_uncertain(db, lease, "lost", "revalidation_failed", report.cost)
        keep_late(db, lease, report, "revalidation_failed")
        fail_after_commit(db, 409, "execution_already_terminal")
    schedule = db.get(m.ExecutionSchedule, execution_id)
    if report.status == "cancelled" and schedule.cancel_requested_at is None:
        raise HTTPException(422, "execution_cancel_not_requested")
    reservation = db.get(m.ExecutionReservation, execution_id)
    lease.state, lease.ended_at, lease.report_hash = "completed", m.utcnow(), report_hash
    execution.status = report.status
    cost = report.cost
    warnings = []
    if cost.state == "provided":
        if budget.units(cost.amount_usd) > reservation.reserved_units:
            warnings.append("reported_cost_exceeds_reserved_limit")
        budget.settle(db, reservation, amount=cost.amount_usd, actor_id=lease.runner_id, attempt_id=lease.attempt_id,
                      measurement_source=cost.measurement_source, pricing_version=cost.pricing_version or "runner-reported@1")
    else:
        reservation.state = "unknown"  # unknown is never zero: the hold stays for reconciliation
    reservation.active = False  # the runner's terminal report is the isolation ack that frees the slot
    record_attempt(db, execution, lease, report.model_dump(mode="json"), "runner_report", warnings)
    runner_audit(db, execution.project_id, "execution.completed", execution.id, lease.runner_id, status=report.status)
    return completion(lease, execution)
