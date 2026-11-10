"""Seal approved inputs and identity before reserving budget; execution stays outside the API."""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import Field
from jwt.exceptions import InvalidTokenError

from app import models as m
from app.domain.tasks import execution_budget as budget
from app.domain.tasks import service as s
from app.domain.tasks.contracts import Contract, canonical_json, digest
from app.domain.tasks.executions import ExecutionManifest
from app.domain.tasks.runner_control import ExecutionPolicy
from app.security import decode_access_token, new_id
from app.timestamps import server_timestamp


class PlanCreate(Contract):
    runner_id: str = Field(min_length=1, max_length=64)
    manifest: ExecutionManifest


class ExecutionCreate(Contract):
    plan_id: str = Field(min_length=1, max_length=64)


def approved(db, actor, project_id, manifest, runner_id):
    project = s.project_access(db, actor, project_id, "read")
    if actor.environment and actor.environment != manifest.environment:
        raise HTTPException(404, "not_found")
    budget.lock_organization(db, project.organization_id)
    runner = s.load(db, actor, "runner", runner_id, project_id=project_id, environment=manifest.environment)
    owner = db.get(m.Membership, (runner.owner_user_id, project.organization_id))
    if runner.disabled_at or owner is None or owner.role != "owner":
        raise HTTPException(409, "runner_unavailable")
    policy_row = db.query(m.ExecutionPolicyRevision).filter_by(project_id=project_id).order_by(m.ExecutionPolicyRevision.version.desc()).first()
    organization_row = budget.current_budget(db, project.organization_id)
    if policy_row is None or organization_row is None:
        raise HTTPException(403, "execution_policy_disabled")
    policy = ExecutionPolicy.model_validate(policy_row.content)
    organization_policy = budget.OrganizationBudget.model_validate(organization_row.content)
    if not policy.enabled or not organization_policy.enabled:
        raise HTTPException(403, "execution_policy_disabled")
    adapter = (manifest.adapter.id, manifest.adapter.version)
    if (manifest.environment not in policy.environments
            or adapter not in {(row.id, row.version) for row in policy.allowed_adapters}
            or adapter not in {(row["id"], row["version"]) for row in runner.capabilities["adapter_versions"]}):
        raise HTTPException(403, "execution_adapter_not_allowed")
    if manifest.mode not in {"local_model", "application_adapter", "agent_behavioral"}:
        raise HTTPException(422, "execution_mode_not_dispatchable")
    limits = manifest.limits
    if (limits.max_cost_usd > policy.max_cost_per_run_usd or limits.max_parallel > policy.max_parallel
            or limits.max_parallel > organization_policy.max_parallel
            or limits.max_parallel > runner.capabilities.get("max_parallel", 1)
            or limits.wall_time_s > policy.max_wall_time_s or limits.max_tool_calls > policy.max_tool_calls
            or limits.max_tokens > policy.max_tokens):
        raise HTTPException(422, "execution_limit_exceeds_policy")
    if manifest.mode == "agent_behavioral" and not manifest.fixture_digests:
        raise HTTPException(422, "agent_execution_requires_fixtures")
    snapshot = s.load(db, actor, "snapshot", manifest.snapshot_id, project_id=project_id, environment=manifest.environment)
    if snapshot.content_hash != manifest.snapshot_hash:
        raise HTTPException(422, "snapshot_hash_mismatch")
    refs = [f"snapshot:{snapshot.id}"]
    for identifier in manifest.candidate.model_versions:
        s.load(db, actor, "model", identifier, project_id=project_id, environment=manifest.environment)
        refs.append(f"model:{identifier}")
    return policy_row, organization_row, s.derived_label(db, refs, project_id, manifest.environment)


def create_plan(db, actor, project_id, payload):
    s.project_access(db, actor, project_id, "write")
    policy, organization, label = approved(db, actor, project_id, payload.manifest, payload.runner_id)
    content = payload.manifest.model_dump(mode="json")
    row = m.ExecutionPlan(id=new_id("execplan"), project_id=project_id, environment=payload.manifest.environment,
        runner_id=payload.runner_id, policy_revision_id=policy.id, organization_budget_revision_id=organization.id,
        manifest_content=canonical_json(content), manifest_hash=digest(content), access_label=label, created_by=actor.id)
    db.add(row)
    return "plan", row


def authorization(db, actor, request, project_id):
    """Persist identifiers/version/expiry, never the original bearer or API secret."""
    if actor.principal_id:
        key_id = request.state.api_key_id
        s.revalidate_principal(db, key_id)
        key = db.get(m.ApiKey, key_id)
        if not {"read", "write", "evaluate"} <= set(key.scopes.split(",")) & actor.scopes:
            raise HTTPException(403, "forbidden")
        return {"kind": "service", "key_id": key_id, "principal_id": actor.principal_id,
                "scopes": sorted(actor.scopes), "actor_id": actor.id}
    try:
        claims = decode_access_token(request.headers["authorization"].removeprefix("Bearer ").strip())
    except InvalidTokenError:
        raise HTTPException(401, "unauthorized") from None
    user = db.query(m.User).filter_by(id=actor.user_id).populate_existing().with_for_update().one_or_none()
    project = db.get(m.Project, project_id)
    membership = db.query(m.Membership).filter_by(user_id=actor.user_id, organization_id=project.organization_id).populate_existing().with_for_update().one_or_none()
    if (user is None or membership is None or membership.role not in {"owner", "member"}
            or claims.get("credential_version", 0) != user.credential_version
            or not claims.get("jti") or "exp" not in claims or db.get(m.RevokedToken, claims["jti"]) is not None):
        raise HTTPException(401, "unauthorized")
    return {"kind": "human", "user_id": user.id, "actor_id": user.id, "credential_version": user.credential_version,
            "token_jti": claims["jti"], "token_expires_at": int(claims["exp"])}


def create_execution(db, actor, request, project_id, payload):
    s.project_access(db, actor, project_id, "evaluate")
    s.project_access(db, actor, project_id, "write")
    plan = s.load(db, actor, "plan", payload.plan_id, project_id=project_id)
    manifest = ExecutionManifest.model_validate_json(plan.manifest_content)
    policy, organization, label = approved(db, actor, project_id, manifest, plan.runner_id)
    if (policy.id, organization.id) != (plan.policy_revision_id, plan.organization_budget_revision_id):
        raise HTTPException(409, "execution_plan_policy_changed")
    context = authorization(db, actor, request, project_id)
    row = m.Execution(id=new_id("execution"), project_id=project_id, environment=plan.environment, origin="controlled_runner",
        mode=manifest.mode, status="queued", manifest_content=plan.manifest_content, manifest_hash=plan.manifest_hash,
        access_label={**label, "source_refs": [f"plan:{plan.id}"]}, created_by=actor.id)
    db.add(row); db.flush()
    db.add(m.ExecutionSchedule(execution_id=row.id, project_id=project_id, plan_id=plan.id, actor_context=context))
    budget.reserve(db, actor, row, policy_revision_id=policy.id, organization_budget_revision_id=organization.id,
                   amount=manifest.limits.max_cost_usd, slots=manifest.limits.max_parallel)
    return "execution", row


def original_actor(db, execution, schedule):
    """Use current scopes/membership and the sealed credential at every runtime boundary."""
    context = schedule.actor_context
    if context["kind"] == "service":
        s.revalidate_principal(db, context["key_id"])
        key = db.get(m.ApiKey, context["key_id"])
        if key.service_principal_id != context["principal_id"] or key.project_id != execution.project_id or key.environment != execution.environment:
            raise HTTPException(401, "unauthorized")
        actor = s.TaskActor(None, key.project_id, key.service_principal_id, key.environment, frozenset(set(key.scopes.split(",")) & set(context["scopes"])))
        s.project_access(db, actor, execution.project_id, "evaluate")
        s.project_access(db, actor, execution.project_id, "write")
        return actor
    user = db.query(m.User).filter_by(id=context["user_id"]).populate_existing().with_for_update().one_or_none()
    if (user is None or user.credential_version != context["credential_version"]
            or context["token_expires_at"] <= datetime.now(timezone.utc).timestamp()
            or db.get(m.RevokedToken, context["token_jti"]) is not None):
        raise HTTPException(401, "unauthorized")
    project = db.get(m.Project, execution.project_id)
    membership = db.query(m.Membership).filter_by(user_id=user.id, organization_id=project.organization_id).populate_existing().with_for_update().one_or_none()
    if membership is None or membership.role not in {"owner", "member"}:
        raise HTTPException(403, "forbidden")
    actor = s.TaskActor(user.id, None, None, None, frozenset())
    s.project_access(db, actor, execution.project_id, "evaluate")
    return actor


def cancel_execution(db, actor, identifier, request):
    execution = db.get(m.Execution, identifier)
    if execution is None:
        raise HTTPException(404, "not_found")
    project = s.project_access(db, actor, execution.project_id, "evaluate")
    budget.lock_project(db, execution.project_id)
    db.expire_all()
    db.info.pop("task_sources", None)
    db.info.pop("task_dataset_projects", None)
    s.project_access(db, actor, execution.project_id, "evaluate")
    if actor.principal_id:
        s.revalidate_principal(db, request.state.api_key_id)
        key = db.get(m.ApiKey, request.state.api_key_id)
        if not {"read", "evaluate"} <= set(key.scopes.split(",")):
            raise HTTPException(403, "forbidden")
    else:
        authorization(db, actor, request, execution.project_id)
    db.refresh(execution)
    membership = db.get(m.Membership, (actor.user_id, project.organization_id)) if actor.user_id else None
    # Owner may stop hidden work without receiving its manifest or source data.
    if membership is None or membership.role != "owner":
        s.load(db, actor, "execution", identifier, permission="evaluate")
    if execution.origin != "controlled_runner":
        raise HTTPException(409, "imported_execution_is_not_cancellable")
    schedule = db.get(m.ExecutionSchedule, identifier)
    if execution.status in {"queued", "running"} and schedule.cancel_requested_at is None:
        schedule.cancel_requested_at = m.utcnow()
        s.audit(db, actor, execution.project_id, "execution.cancel.requested", f"execution:{identifier}")
        if execution.status == "queued":
            reservation = db.get(m.ExecutionReservation, identifier)
            budget.settle(db, reservation, amount="0", actor_id=actor.id, measurement_source="server_cancelled_before_lease", pricing_version="execution-budget@1")
            reservation.active = False
            execution.status = "cancelled"
    db.flush()
    return {"id": identifier, "status": execution.status, "cancel_requested_at": server_timestamp(schedule.cancel_requested_at).isoformat() if schedule.cancel_requested_at else None}
