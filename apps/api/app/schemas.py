from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.timestamps import ServerTimestamp


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    created_at: ServerTimestamp


class ProjectCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    default_environment: str = Field(default="prod", pattern=r"^(dev|staging|prod)$")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    slug: str
    description: str | None = None
    default_environment: str = "prod"
    created_at: ServerTimestamp


class ProjectUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    default_environment: str | None = Field(default=None, pattern=r"^(dev|staging|prod)$")


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    joined_at: ServerTimestamp


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Literal["member", "viewer"] = "viewer"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            if "\r" in value or "\n" in value:
                raise ValueError("invalid_email")
            value = value.strip().lower()
            from email.headerregistry import Address
            Address(addr_spec=value)
        return value


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]{43}$")


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    email: str
    role: str
    invited_by_user_id: str | None
    status: str
    created_at: ServerTimestamp
    expires_at: ServerTimestamp
    accepted_at: ServerTimestamp | None
    revoked_at: ServerTimestamp | None


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["member", "viewer"]


class OwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    environment: str = Field(pattern=r"^(dev|staging|prod)$")
    # "evaluate" spends judge budget, so it is never a default.
    scopes: list[str] = Field(default_factory=lambda: ["ingest", "read"])
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        unknown = set(value) - {"ingest", "read", "evaluate"}
        if unknown:
            raise ValueError(f"unknown scopes: {sorted(unknown)}")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        now = datetime.now(timezone.utc)
        if value.tzinfo is None or value.utcoffset() is None:
            now = now.replace(tzinfo=None)
        if value <= now:
            raise ValueError("expires_at_must_be_future")
        return value


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prefix: str
    name: str
    environment: str
    scopes: list[str]
    rate_limit_per_minute: int
    created_at: ServerTimestamp
    revoked_at: ServerTimestamp | None = None
    expires_at: datetime | None = None


class ApiKeyCreateOut(ApiKeyOut):
    key: str


class TraceEventIn(BaseModel):
    type: str
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)


class TraceSpanIn(BaseModel):
    client_span_id: str
    parent_client_span_id: str | None = None
    type: str
    name: str
    started_at: datetime
    ended_at: datetime
    status: str = Field(pattern=r"^(ok|error)$")
    provider: str | None = None
    model: str | None = None
    prompt_version_ref: str | None = None
    messages_in: list[dict] | None = None
    messages_out: list[dict] | None = None
    tools: list[dict] | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    fallback_from_client_span_id: str | None = None
    input: dict | None = None
    output: dict | None = None
    error: dict | None = None
    metadata: dict = Field(default_factory=dict)
    events: list[TraceEventIn] = Field(default_factory=list)


class TraceIn(BaseModel):
    client_trace_id: str | None = None
    name: str
    service: str | None = None
    environment: str = Field(pattern=r"^(dev|staging|prod)$")
    started_at: datetime
    ended_at: datetime
    status: str = Field(pattern=r"^(ok|error|partial)$")
    tags: dict = Field(default_factory=dict)
    user_ref: str | None = None
    metadata: dict = Field(default_factory=dict)
    spans: list[TraceSpanIn] = Field(default_factory=list)


class TraceBatchIn(BaseModel):
    traces: list[TraceIn]


class TraceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    project_id: str
    organization_id: str
    client_trace_id: str | None = None
    name: str
    service: str | None = None
    environment: str
    status: str
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    tags: dict
    user_ref: str | None = None
    metadata: dict = Field(alias="metadata_json")
    redacted: bool = False
    created_at: ServerTimestamp
    # Populated at the route layer (list + detail) — not a column. Marked
    # optional so model_validate(trace) does not complain.
    cost_source: str | None = None


class TraceFlagIn(BaseModel):
    reason: str = Field(
        pattern=r"^(manual|schema_mismatch|low_quality|low_confidence|timeout|cost_spike|other)$"
    )
    note: str | None = Field(default=None, max_length=2000)


class TraceFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trace_id: str
    org_id: str
    user_id: str
    reason: str
    note: str | None = None
    created_at: ServerTimestamp


class BulkTraceFlagIn(TraceFlagIn):
    trace_ids: list[str] = Field(min_length=1, max_length=100)


class BulkTraceFlagOut(BaseModel):
    data: list[TraceFlagOut]
    created: int


class TraceRerunIn(BaseModel):
    model: str | None = Field(default=None, max_length=128)
    variables: dict = Field(default_factory=dict)


class TraceRerunOut(BaseModel):
    new_trace_id: str
    status: str
    replay_status: str = "queued"


class TraceCompareIn(BaseModel):
    left_trace_id: str
    right_trace_id: str


class TraceCompareOut(BaseModel):
    left: TraceOut
    right: TraceOut
    diff: dict


# ── Phase 4: Rubrics & Evaluations ──────────────────────────────────────────

class RubricCreate(BaseModel):
    yaml_source: str


class RubricVersionCreate(BaseModel):
    yaml_source: str
    changelog: str | None = None


class EvaluatorRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str | None = None
    type: str
    weight: float
    fail_fast: bool
    enabled: bool
    ord: int


class RubricVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rubric_id: str
    version: int
    yaml_source: str
    parsed_spec: dict
    created_by: str
    created_at: ServerTimestamp


class RubricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    slug: str
    description: str | None = None
    current_version: int
    threshold: float
    created_at: ServerTimestamp


class EvaluationRunRequest(BaseModel):
    trace_id: str
    rubric_id: str
    rubric_version: int | None = None
    triggered_by: str = "api"


class EvaluationBatchIn(BaseModel):
    rubric_id: str
    rubric_version: int | None = None
    trace_ids: list[str] | None = Field(default=None, max_length=500)
    environment: str | None = Field(default=None, pattern=r"^(dev|staging|prod)$")
    batch: str | None = Field(default=None, max_length=255)
    name_contains: str | None = Field(default=None, max_length=255)
    since: datetime | None = None
    limit: int = Field(default=100, ge=1, le=500)


class EvaluationScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    evaluator_slug: str
    score: float
    passed: bool
    reasoning: str | None = None
    raw_output: dict | None = None
    cost_usd: float | None = None
    latency_ms: int


class EvaluationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    project_id: str
    trace_id: str
    rubric_id: str
    rubric_version: int
    triggered_by: str
    status: str
    aggregate_score: float | None = None
    passed: bool | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    started_at: ServerTimestamp | None = None
    completed_at: ServerTimestamp | None = None
    error: dict | None = Field(default=None, alias="error_json")
    run_metadata: dict
    created_at: ServerTimestamp


# Phase 5: prompts, datasets and experiments


class PromptCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    template: str = Field(min_length=1)
    variables: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    changelog: str | None = None


class PromptVersionCreate(BaseModel):
    template: str = Field(min_length=1)
    variables: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    changelog: str | None = None


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    slug: str
    description: str | None = None
    current_version: int
    created_at: ServerTimestamp


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    prompt_id: str
    version: int
    template: str
    variables: dict
    metadata: dict = Field(alias="metadata_json")
    changelog: str | None = None
    created_by: str
    created_at: ServerTimestamp


class DatasetCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    source: str = Field(default="manual", min_length=2, max_length=64)


class DatasetItemIn(BaseModel):
    input: dict = Field(default_factory=dict)
    expected_output: dict | None = None
    metadata: dict = Field(default_factory=dict)


class DatasetItemsCreate(BaseModel):
    items: list[DatasetItemIn] = Field(default_factory=list)


class DatasetBuildFromTraces(BaseModel):
    environment: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    name_contains: str | None = None


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    slug: str
    description: str | None = None
    source: str
    created_at: ServerTimestamp


class DatasetItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    dataset_id: str
    ord: int
    input: dict
    expected_output: dict | None = None
    metadata: dict = Field(alias="metadata_json")
    created_at: ServerTimestamp


class ExperimentVariantIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    prompt_version_ref: str | None = None
    model: str | None = None
    params: dict = Field(default_factory=dict)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    dataset_id: str
    rubric_id: str
    variants: list[ExperimentVariantIn] = Field(min_length=1)
    pass_criteria: dict = Field(default_factory=dict)
    baseline_variant: str | None = None


class ExperimentRunRequest(BaseModel):
    triggered_by: str = "api"


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    name: str
    dataset_id: str
    rubric_id: str
    variants: list
    pass_criteria: dict
    baseline_variant: str | None = None
    created_at: ServerTimestamp


class ExperimentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    project_id: str
    status: str
    triggered_by: str
    passed: bool | None = None
    by_variant: dict
    comparisons: dict
    criteria_failures: list
    run_metadata: dict
    started_at: ServerTimestamp | None = None
    completed_at: ServerTimestamp | None = None
    created_at: ServerTimestamp


class HumanFeedbackCreate(BaseModel):
    source: str = Field(default="dashboard", min_length=2, max_length=32)
    thumbs: str | None = Field(default=None, pattern=r"^(up|down)$")
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)
    user_ref: str | None = None
    correction: dict | None = None


class HumanFeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    trace_id: str
    source: str
    thumbs: str | None = None
    rating: int | None = None
    comment: str | None = None
    tags: list
    user_ref: str | None = None
    correction: dict | None = None
    created_at: ServerTimestamp


class ExportJobCreate(BaseModel):
    project_id: str
    filters: dict = Field(default_factory=dict)
    format: str = Field(default="jsonl", pattern=r"^(jsonl)$")


class ExportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    status: str
    format: str
    filters: dict
    row_count: int
    file_path: str | None = None
    file_size_bytes: int | None = None
    error: str | None = None
    expires_at: ServerTimestamp | None = None
    created_by: str | None = None
    created_at: ServerTimestamp
    completed_at: ServerTimestamp | None = None


class ExportListResponse(BaseModel):
    data: list[ExportJobOut]
    next_cursor: str | None = None


class AttentionItemOut(BaseModel):
    trace_id: str
    cause: str
    service: str | None = None
    at: ServerTimestamp


class AttentionResponse(BaseModel):
    count: int
    items: list[AttentionItemOut]


class CoverageItemOut(BaseModel):
    rubric_id: str
    rubric_slug: str
    coverage: float
    runs_7d: int


class CoverageResponse(BaseModel):
    data: list[CoverageItemOut]


class CliJudgeOptionOut(BaseModel):
    provider: str
    model: str
    status: str
    version: str | None = None


class CliJudgeOptionsOut(BaseModel):
    data: list[CliJudgeOptionOut]


class EvaluationSummaryOut(BaseModel):
    active_rubrics: int
    runs_7d: int
    pass_rate: float | None = None
    cost_usd: float | None = None


class PromptUsageTraceOut(BaseModel):
    trace_id: str
    name: str
    service: str | None = None
    environment: str
    status: str
    prompt_version_ref: str | None = None
    used_at: ServerTimestamp


class PromptUsageOut(BaseModel):
    prompt_id: str
    usage_count: int
    usage_count_truncated: bool = False
    traces: list[PromptUsageTraceOut]


class RagCitationOut(BaseModel):
    rank: int
    title: str | None = None
    score: float | None = None
    source: str | None = None
    chunk: str | None = None


class RagClaimOut(BaseModel):
    text: str
    grounded: bool
    cite: str | None = None


class RagClaimChunkOut(BaseModel):
    claim: str
    chunk: str
    score: float | None = None


class RagConsolidatedOut(BaseModel):
    retrieved_docs: int
    avg_score: float | None = None
    grounded_claims: int | None = None
    ungrounded_claims: int | None = None
    support_rate: float | None = None
    claims_unavailable: bool = False
    hallucination_risk: str
    answer_preview: str | None = None
    citations: list[RagCitationOut]
    claims: list[RagClaimOut]
    claim_to_chunk: list[RagClaimChunkOut]
    redacted: bool = False


class SdkStatusOut(BaseModel):
    p95_ingestion_ms: int
    spans_per_minute: float
    last_event_at: datetime | None = None
    services_seen: list[str]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    title: str
    meta: dict
    created_at: ServerTimestamp
    read_at: ServerTimestamp | None = None


class NotificationListResponse(BaseModel):
    data: list[NotificationOut]
    unread_count: int


class NotificationMarkReadIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


class QualityGateSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    min_score: float = Field(default=0.8, ge=0, le=1)
    max_ungrounded_rate: float = Field(default=0.05, ge=0, le=1)
    max_avg_cost_usd: float = Field(default=0.05, ge=0)
    max_p95_ms: int = Field(default=2000, ge=0, le=86400000)
    require_zero_critical: bool = True


class QualityGateConfigOut(QualityGateSettings):
    model_config = ConfigDict(from_attributes=True, allow_inf_nan=False)

    project_id: str
    configured: bool
    updated_at: ServerTimestamp | None = None


class QualityGateReason(BaseModel):
    metric: Literal["configuration", "quality", "ungrounded", "avg_cost", "p95", "critical"]
    status: Literal["pass", "review", "fail"]
    code: str
    observed: float | None
    threshold: float | None
    sample_count: int


class QualityGateMetrics(BaseModel):
    trace_count: int
    evaluated_trace_count: int
    rag_trace_count: int
    grounding_trace_count: int
    critical_checked_trace_count: int
    avg_score: float | None
    ungrounded_rate: float | None
    avg_cost_usd: float | None
    latency_p95_ms: int | None
    critical_violations: int | None


class QualityGateStatusOut(BaseModel):
    project_id: str
    status: Literal["pass", "review", "fail"]
    window: Literal["24h", "7d", "30d"]
    environment: str | None
    calculated_at: ServerTimestamp
    config: QualityGateConfigOut
    metrics: QualityGateMetrics
    reasons: list[QualityGateReason]


class EvaluationSamplingSettings(BaseModel):
    enabled: bool = False
    percentage: float = Field(default=0, ge=0, le=100, allow_inf_nan=False)
    rubric_id: str | None = Field(default=None, min_length=1, max_length=64)
    rubric_version: int | None = Field(default=None, ge=1)


class EvaluationSamplingConfigOut(EvaluationSamplingSettings):
    model_config = ConfigDict(from_attributes=True)
    updated_at: ServerTimestamp | None = None


class EvaluationSamplingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    trace_id: str
    rubric_id: str
    rubric_version: int
    status: str
    reason: str | None
    run_id: str | None
    dispatch_attempts: int
    execution_attempts: int
    next_attempt_at: ServerTimestamp
    created_at: ServerTimestamp
    updated_at: ServerTimestamp

    @computed_field
    @property
    def retry_warning(self) -> str | None:
        if self.status == "uncertain":
            return "A tentativa pode ter sido cobrada pelo provider sem resultado salvo. Tentar novamente pode gerar nova cobrança."
        return None


class EvaluationSamplingRetryIn(BaseModel):
    confirm_possible_charge: bool = False
