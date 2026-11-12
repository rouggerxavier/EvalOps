"""Import external harness evidence; no dispatch, budget reservation or process execution."""
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, model_validator

from app import models as m
from app.domain.tasks import service as s
from app.domain.tasks.contracts import Contract, Environment, canonical_json, digest
from app.security import new_id

Hash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Money = Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), max_digits=18, decimal_places=8)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class Candidate(Contract):
    application_ref: str = Field(min_length=1, max_length=255)
    code_commit: str = Field(min_length=1, max_length=128)
    code_dirty: bool = Field(strict=True)
    patch_digest: Hash | None = None
    config_digest: Hash
    model_versions: tuple[Identifier, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def dirty_patch(self):
        if self.code_dirty and not self.patch_digest:
            raise ValueError("dirty_code_requires_patch_digest")
        if len(set(self.model_versions)) != len(self.model_versions):
            raise ValueError("duplicate_model_version")
        return self


class Adapter(Contract):
    id: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=128)
    environment_digest: Hash
    runtime: str = Field(min_length=1, max_length=255)
    dependency_lock_digest: Hash | None = None
    hardware: str | None = Field(default=None, max_length=255)


class ExecutionLimits(Contract):
    max_cost_usd: Money
    wall_time_s: int = Field(ge=1, le=86400, strict=True)
    max_tool_calls: int = Field(ge=0, le=100000, strict=True)
    max_tokens: int = Field(ge=0, le=10000000, strict=True)
    max_parallel: int = Field(ge=1, le=100, strict=True)


class ExecutionManifest(Contract):
    schema_version: Literal[1] = 1
    mode: Literal["offline_predictions", "local_model", "application_adapter", "llm_call_replay", "agent_behavioral"]
    environment: Environment
    snapshot_id: Identifier
    snapshot_hash: Hash
    candidate: Candidate
    adapter: Adapter
    evaluator_versions: tuple[Identifier, ...] = Field(default=(), max_length=100)
    initial_state_digest: Hash
    fixture_digests: tuple[Hash, ...] = Field(default=(), max_length=100)
    seed: int | None = Field(default=None, ge=-(2**63), le=2**63-1, strict=True)
    repetitions: int = Field(default=1, ge=1, le=100, strict=True)
    limits: ExecutionLimits
    effects_policy: Literal["fixtures_only"] = "fixtures_only"


class ReportedCost(Contract):
    state: Literal["provided", "unknown", "not_measured"]
    amount_usd: Money | None = None
    measurement_source: str | None = Field(default=None, max_length=255)
    pricing_version: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def explicit_measurement(self):
        if self.state == "provided":
            if self.amount_usd is None or not self.measurement_source:
                raise ValueError("provided_cost_requires_amount_and_source")
        elif self.amount_usd is not None:
            raise ValueError("unknown_cost_cannot_be_zero")
        return self


class ImportedResult(Contract):
    status: Literal["succeeded", "failed", "timed_out", "cancelled", "uncertain"]
    exit_reason: str = Field(min_length=1, max_length=2000)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    prediction_set_id: Identifier | None = None
    trace_ids: tuple[Identifier, ...] = Field(default=(), max_length=100)
    capture_status: Literal["complete", "partial", "uncertain"]
    cost: ReportedCost

    @model_validator(mode="after")
    def coherent_capture(self):
        if self.ended_at < self.started_at:
            raise ValueError("negative_duration")
        if self.status == "succeeded" and self.prediction_set_id is None:
            raise ValueError("successful_import_requires_predictions")
        if len(set(self.trace_ids)) != len(self.trace_ids):
            raise ValueError("duplicate_trace_id")
        return self


class ExecutionImport(Contract):
    manifest: ExecutionManifest
    result: ImportedResult


def import_execution(db, actor, project_id, payload):
    s.project_access(db, actor, project_id, "write")
    manifest, result = payload.manifest, payload.result
    if actor.environment and actor.environment != manifest.environment:
        raise HTTPException(404, "not_found")
    snapshot = s.load(db, actor, "snapshot", manifest.snapshot_id, project_id=project_id, environment=manifest.environment)
    if snapshot.content_hash != manifest.snapshot_hash:
        raise HTTPException(422, "snapshot_hash_mismatch")
    refs = [f"snapshot:{snapshot.id}"]
    for identifier in manifest.candidate.model_versions:
        s.load(db, actor, "model", identifier, project_id=project_id, environment=manifest.environment)
        refs.append(f"model:{identifier}")
    bindings = {"snapshot_hash": snapshot.content_hash, "prediction_hash": None}
    if result.prediction_set_id:
        predictions = s.load(db, actor, "predictions", result.prediction_set_id, project_id=project_id, environment=manifest.environment)
        if predictions.snapshot_id != snapshot.id or predictions.model_version_id not in manifest.candidate.model_versions:
            raise HTTPException(422, "execution_prediction_binding_mismatch")
        bindings["prediction_hash"] = predictions.content_hash
        refs.append(f"predictions:{predictions.id}")
    for identifier in result.trace_ids:
        s.load(db, actor, "trace", identifier, project_id=project_id, environment=manifest.environment)
        refs.append(f"trace:{identifier}")
    label = s.derived_label(db, refs, project_id, manifest.environment)
    manifest_content = canonical_json(manifest.model_dump(mode="json"))
    row = m.Execution(id=new_id("execution"), project_id=project_id, environment=manifest.environment,
        mode=manifest.mode, status=result.status, manifest_content=manifest_content,
        manifest_hash=digest(manifest.model_dump(mode="json")), access_label=label, created_by=actor.id)
    db.add(row); db.flush()
    warnings = ["external_capture_not_verified", "limits_declared_not_enforced_by_importer"]
    if result.cost.state == "provided" and result.cost.amount_usd > manifest.limits.max_cost_usd:
        warnings.append("reported_cost_exceeds_declared_limit")
    if (result.ended_at - result.started_at).total_seconds() > manifest.limits.wall_time_s:
        warnings.append("reported_duration_exceeds_declared_limit")
    content = {**result.model_dump(mode="json"), "input_bindings": bindings, "producer": "external_harness",
               "provenance": "partial", "warnings": warnings, "budget_reserved": None, "decision": None}
    attempt = m.ExecutionAttempt(id=new_id("attempt"), execution_id=row.id, project_id=project_id,
        environment=manifest.environment, attempt_number=1, result_content=canonical_json(content), result_hash=digest(content),
        access_label={**label, "source_refs": [f"execution:{row.id}"]})
    db.add(attempt)
    return "execution", row
