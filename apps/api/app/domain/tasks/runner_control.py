"""Owner-controlled policy and runner identity; dispatch remains disabled until the fixture runtime exists."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator

from app import models as m
from app.domain.tasks import service as s
from app.domain.tasks.contracts import Contract, Environment, digest
from app.domain.tasks.executions import Money
from app.security import new_id, verify_api_key
from app.timestamps import server_timestamp


class AdapterVersion(Contract):
    id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=128)


class ExecutionPolicy(Contract):
    enabled: bool = Field(default=False, strict=True)
    environments: tuple[Environment, ...] = Field(default=("dev",), min_length=1, max_length=3)
    allowed_adapters: tuple[AdapterVersion, ...] = Field(default=(), max_length=100)
    max_cost_per_run_usd: Money = Decimal("0")
    monthly_budget_usd: Money = Decimal("0")
    max_parallel: int = Field(default=1, ge=1, le=100, strict=True)
    max_wall_time_s: int = Field(default=300, ge=1, le=86400, strict=True)
    max_tool_calls: int = Field(default=20, ge=0, le=100000, strict=True)
    max_tokens: int = Field(default=10000, ge=0, le=10000000, strict=True)
    effects_policy: Literal["fixtures_only"] = "fixtures_only"

    @model_validator(mode="after")
    def unique_capabilities(self):
        if len(set(self.environments)) != len(self.environments) or len({(row.id, row.version) for row in self.allowed_adapters}) != len(self.allowed_adapters):
            raise ValueError("duplicate_policy_capability")
        if self.enabled and not self.allowed_adapters:
            raise ValueError("enabled_policy_requires_adapter")
        if self.max_cost_per_run_usd > self.monthly_budget_usd:
            raise ValueError("run_budget_exceeds_monthly_budget")
        return self


class RunnerRegistration(Contract):
    name: str = Field(min_length=1, max_length=255)
    environments: tuple[Environment, ...] = Field(min_length=1, max_length=3)
    adapter_versions: tuple[AdapterVersion, ...] = Field(min_length=1, max_length=100)
    isolation: Literal["client_managed"] = "client_managed"
    max_parallel: int = Field(default=1, ge=1, le=100, strict=True)

    @model_validator(mode="after")
    def unique_capabilities(self):
        if len(set(self.environments)) != len(self.environments) or len({(row.id, row.version) for row in self.adapter_versions}) != len(self.adapter_versions):
            raise ValueError("duplicate_runner_capability")
        return self


def metadata_label(environments):
    return {"label_schema_version": 1, "access_revision": 1, "origin_environments": [], "allowed_environments": list(environments), "source_refs": []}


def policy_revision(db, actor, project_id, policy, expected_version):
    s.project_access(db, actor, project_id, "admin")
    current = db.query(m.ExecutionPolicyRevision).filter_by(project_id=project_id).order_by(m.ExecutionPolicyRevision.version.desc()).first()
    if expected_version != (current.version if current else 0):
        raise HTTPException(409, "execution_policy_revision_conflict")
    content = policy.model_dump(mode="json")
    row = m.ExecutionPolicyRevision(id=new_id("policy"), project_id=project_id, version=expected_version+1,
        content=content, content_hash=digest(content), access_label=metadata_label(policy.environments), created_by=actor.user_id)
    db.add(row)
    return "policy", row


def register_runner(db, actor, project_id, payload):
    s.project_access(db, actor, project_id, "admin")
    row = m.Runner(id=new_id("runner"), project_id=project_id, name=payload.name, owner_user_id=actor.user_id,
        capabilities=payload.model_dump(mode="json", exclude={"name"}), access_label=metadata_label(payload.environments))
    db.add(row)
    return "runner", row


def authenticate_runner(db, runner_id, raw):
    """Separate credential store: this identity never receives ordinary project read scopes."""
    if not raw:
        raise HTTPException(401, "unauthorized")
    runner = db.get(m.Runner, runner_id)
    if runner is None:
        raise HTTPException(401, "unauthorized")
    key = next((row for row in db.query(m.RunnerCredential).filter_by(runner_id=runner_id, prefix=raw[:14], revoked_at=None)
                if verify_api_key(raw, row.hash)), None)
    now = datetime.now(timezone.utc)
    project = db.get(m.Project, runner.project_id)
    owner = db.get(m.Membership, (runner.owner_user_id, project.organization_id)) if project else None
    if (key is None or server_timestamp(key.expires_at) <= now or runner.disabled_at
            or owner is None or owner.role != "owner"):
        raise HTTPException(401, "unauthorized")
    return runner, key
