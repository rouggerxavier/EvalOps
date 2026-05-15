from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship()


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    prefix: Mapped[str] = mapped_column(String(64), index=True)
    hash: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(255))
    environment: Mapped[str] = mapped_column(String(16))
    scopes: Mapped[str] = mapped_column(String(255), default="ingest,read")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (UniqueConstraint("project_id", "client_trace_id", name="uq_traces_project_client"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(String(64), index=True)
    client_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    total_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    tags: Mapped[dict] = mapped_column(JSON, default=dict)
    user_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    redacted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # G-21: soft delete — set instead of hard DELETE; NULL means active.
    # Migration for existing DBs: ALTER TABLE traces ADD COLUMN deleted_at DATETIME;
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)
    parent_span_id: Mapped[str | None] = mapped_column(ForeignKey("spans.id", ondelete="CASCADE"), nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    messages_in: Mapped[list | None] = mapped_column(JSON, nullable=True)
    messages_out: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    fallback_from_span_id: Mapped[str | None] = mapped_column(
        ForeignKey("spans.id", ondelete="SET NULL"),
        nullable=True,
    )
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    span_id: Mapped[str] = mapped_column(ForeignKey("spans.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


# ── Phase 4: Evaluation ──────────────────────────────────────────────────────

class Rubric(Base):
    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_rubrics_project_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    threshold: Mapped[float] = mapped_column(Numeric(4, 3), default=0.7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list["RubricVersion"]] = relationship(back_populates="rubric", cascade="all, delete-orphan")


class RubricVersion(Base):
    __tablename__ = "rubric_versions"
    __table_args__ = (UniqueConstraint("rubric_id", "version", name="uq_rubric_versions_rubric_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    yaml_source: Mapped[str] = mapped_column(Text())
    parsed_spec: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    rubric: Mapped["Rubric"] = relationship(back_populates="versions")
    evaluator_rows: Mapped[list["EvaluatorRow"]] = relationship(back_populates="rubric_version", cascade="all, delete-orphan")


class EvaluatorRow(Base):
    """Normalized evaluator config stored per rubric version."""
    __tablename__ = "evaluators"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    rubric_version_id: Mapped[str] = mapped_column(ForeignKey("rubric_versions.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(255))  # YAML id field
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    fail_fast: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ord: Mapped[int] = mapped_column(Integer, default=0)

    rubric_version: Mapped["RubricVersion"] = relationship(back_populates="evaluator_rows")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (UniqueConstraint("trace_id", "rubric_id", "rubric_version", name="uq_eval_runs_trace_rubric_ver"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"))
    rubric_version: Mapped[int] = mapped_column(Integer)
    triggered_by: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    aggregate_score: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_json: Mapped[dict | None] = mapped_column("error", JSON, nullable=True)
    run_metadata: Mapped[dict] = mapped_column("run_metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scores: Mapped[list["EvaluationScore"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class EvaluationScore(Base):
    __tablename__ = "evaluation_scores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True)
    evaluator_row_id: Mapped[str] = mapped_column(ForeignKey("evaluators.id", ondelete="RESTRICT"))
    evaluator_slug: Mapped[str] = mapped_column(String(255))  # denormalized for convenience
    score: Mapped[float] = mapped_column(Numeric(6, 4))
    passed: Mapped[bool] = mapped_column(Boolean)
    reasoning: Mapped[str | None] = mapped_column(Text(), nullable=True)
    raw_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped["EvaluationRun"] = relationship(back_populates="scores")


# Phase 5: prompts, datasets and experiments


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_prompts_project_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list["PromptVersion"]] = relationship(back_populates="prompt", cascade="all, delete-orphan")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_prompt_versions_prompt_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(Text())
    variables: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    changelog: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    prompt: Mapped["Prompt"] = relationship(back_populates="versions")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_datasets_project_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["DatasetItem"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    ord: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    dataset: Mapped["Dataset"] = relationship(back_populates="items")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), index=True)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"), index=True)
    variants: Mapped[list] = mapped_column(JSON, default=list)
    pass_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    triggered_by: Mapped[str] = mapped_column(String(32), default="api")
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    by_variant: Mapped[dict] = mapped_column(JSON, default=dict)
    comparisons: Mapped[dict] = mapped_column(JSON, default=dict)
    criteria_failures: Mapped[list] = mapped_column(JSON, default=list)
    run_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Phase 6: feedback, exports, mock billing/usage


class HumanFeedback(Base):
    __tablename__ = "human_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="dashboard")
    thumbs: Mapped[str | None] = mapped_column(String(8), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    user_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    format: Mapped[str] = mapped_column(String(16), default="jsonl")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    monthly_trace_limit: Mapped[int] = mapped_column(Integer, default=1000)
    monthly_eval_limit: Mapped[int] = mapped_column(Integer, default=500)
    monthly_export_limit: Mapped[int] = mapped_column(Integer, default=10)
    # Phase 6 (G-07): per-plan span/token quotas. Migration for existing DBs:
    #   ALTER TABLE plans ADD COLUMN monthly_span_limit INTEGER NOT NULL DEFAULT 50000;
    #   ALTER TABLE plans ADD COLUMN monthly_token_limit BIGINT NOT NULL DEFAULT 5000000;
    monthly_span_limit: Mapped[int] = mapped_column(Integer, default=50000)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, default=5_000_000)
    # Phase 6 (G-12): per-plan judge budget cap. Migration for existing DBs:
    #   ALTER TABLE plans ADD COLUMN monthly_judge_budget_usd NUMERIC(12,6) NOT NULL DEFAULT 20;
    monthly_judge_budget_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("organization_id", "period", name="uq_usage_org_period"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    traces_ingested: Mapped[int] = mapped_column(Integer, default=0)
    evaluations_run: Mapped[int] = mapped_column(Integer, default=0)
    exports_created: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    # Phase 6 (G-07): track spans/tokens monthly. Migration for existing DBs:
    #   ALTER TABLE usage_counters ADD COLUMN spans_ingested INTEGER NOT NULL DEFAULT 0;
    #   ALTER TABLE usage_counters ADD COLUMN tokens_ingested BIGINT NOT NULL DEFAULT 0;
    spans_ingested: Mapped[int] = mapped_column(Integer, default=0)
    tokens_ingested: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Nullable since Phase 2 (G-16): auth.failed_login has no org context.
    # Prod databases created before this change need a manual
    # `ALTER TABLE audit_logs ALTER COLUMN organization_id DROP NOT NULL;`
    # (Alembic adoption is Phase 7 — until then, drop+recreate in dev only.)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RevokedToken(Base):
    """JWT denylist for server-side logout (G-15).

    Tokens issued *before* this rollout have no ``jti`` and continue to
    work until their natural ``exp``. Tokens issued after carry a ``jti``
    that lands here on logout; ``get_current_user`` rejects matches.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
