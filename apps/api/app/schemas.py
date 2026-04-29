from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    created_at: datetime


class ProjectCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    slug: str
    description: str | None = None
    created_at: datetime


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    environment: str = Field(pattern=r"^(dev|staging|prod)$")
    scopes: list[str] = Field(default_factory=lambda: ["ingest", "read"])


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prefix: str
    name: str
    environment: str
    scopes: list[str]
    rate_limit_per_minute: int
    created_at: datetime
    revoked_at: datetime | None = None


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
    created_at: datetime
