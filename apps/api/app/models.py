from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
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
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordReset(Base):
    """One latest request per user; raw tokens exist only in worker memory/email."""
    __tablename__ = "password_resets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    membership_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
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


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'viewer')", name="ck_organization_invitations_role"),
        CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed', 'accepted', 'revoked')",
                        name="ck_organization_invitations_status"),
        Index("ix_organization_invitations_listing", "organization_id", "created_at", "id"),
        Index("ix_organization_invitations_email", "organization_id", "email"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(16))
    invited_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    default_environment: Mapped[str] = mapped_column(String(16), default="prod", server_default="prod")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship()


class QualityGateConfig(Base):
    """One opt-in quality policy per project; no changes to trace/eval storage."""
    __tablename__ = "quality_gate_configs"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    min_score: Mapped[float] = mapped_column(Float, nullable=False)
    max_ungrounded_rate: Mapped[float] = mapped_column(Float, nullable=False)
    max_avg_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    max_p95_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    require_zero_critical: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ServicePrincipal(Base):
    __tablename__ = "service_principals"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_principal_project"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (ForeignKeyConstraint(["service_principal_id", "project_id"],
        ["service_principals.id", "service_principals.project_id"], name="fk_key_principal_project"),)

    service_principal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Trace(Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("project_id", "client_trace_id", name="uq_traces_project_client"),
        # Postgres-only expression indexes, same as migration 0006_prompt_ref_index.
        Index("ix_traces_metadata_prompt_ref", text("(metadata->>'prompt_ref')")).ddl_if(dialect="postgresql"),
        Index("ix_traces_metadata_prompt_version_ref", text("(metadata->>'prompt_version_ref')")).ddl_if(
            dialect="postgresql"
        ),
    )

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


class TraceFlag(Base):
    __tablename__ = "trace_flags"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    __table_args__ = (
        UniqueConstraint("trace_id", "rubric_id", "rubric_version", name="uq_eval_runs_trace_rubric_ver"),
        # Same as migration 0007_eval_runs_trace_created.
        Index("ix_evaluation_runs_trace_created", "trace_id", text("created_at DESC")),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)
    rubric_id: Mapped[str] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"))
    rubric_version: Mapped[int] = mapped_column(Integer)
    triggered_by: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    aggregate_score: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
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
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
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

    task_type: Mapped[str] = mapped_column(String(32), default="text", server_default="text")
    task_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    access_label: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_datasets_project_slug"), UniqueConstraint("id", "project_id", name="uq_dataset_project"))

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["DatasetItem"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    access_label: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
    __table_args__ = (CheckConstraint("(kind = 'legacy_synthetic' AND rubric_id IS NOT NULL) OR (kind = 'task_comparison' AND snapshot_id IS NOT NULL)", name="ck_experiment_kind"),
        ForeignKeyConstraint(["snapshot_id", "project_id"], ["dataset_snapshots.id", "dataset_snapshots.project_id"], name="fk_experiment_snapshot"),)

    kind: Mapped[str] = mapped_column(String(32), default="legacy_synthetic", server_default="legacy_synthetic")
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), index=True)
    rubric_id: Mapped[str | None] = mapped_column(ForeignKey("rubrics.id", ondelete="RESTRICT"), nullable=True, index=True)
    variants: Mapped[list] = mapped_column(JSON, default=list)
    pass_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_variant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_experiment_run_project"),
        CheckConstraint("decision IS NULL OR decision IN ('pass','fail','review','inconclusive')", name="ck_run_decision"),
        CheckConstraint("(kind = 'legacy_synthetic' AND decision IS NULL) OR (kind = 'task_comparison' AND passed IS NULL AND (status = 'running' OR decision IS NOT NULL))", name="ck_run_kind_decision"),
    )
    kind: Mapped[str] = mapped_column(String(32), default="legacy_synthetic", server_default="legacy_synthetic")
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_reasons: Mapped[list] = mapped_column(JSON, default=list)


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
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


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
    # Judge-budget spend of trace replays (reserved at enqueue, settled by the worker); server-only.
    replay_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0, server_default="0")
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


class EvaluationSamplingConfig(Base):
    __tablename__ = "evaluation_sampling_configs"
    __table_args__ = (
        CheckConstraint("percentage >= 0 AND percentage <= 100", name="ck_sampling_percentage"),
        ForeignKeyConstraint(["rubric_id", "rubric_version"], ["rubric_versions.rubric_id", "rubric_versions.version"], ondelete="RESTRICT"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    percentage: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    rubric_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rubric_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EvaluationSamplingJob(Base):
    """Durable selection/outbox: one automatic evaluation per newly accepted trace."""
    __tablename__ = "evaluation_sampling_jobs"
    __table_args__ = (
        ForeignKeyConstraint(["rubric_id", "rubric_version"], ["rubric_versions.rubric_id", "rubric_versions.version"], ondelete="RESTRICT"),
        Index("ix_sampling_jobs_dispatch", "status", "next_attempt_at"),
    )

    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    rubric_id: Mapped[str] = mapped_column(String(64))
    rubric_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="SET NULL"), nullable=True)
    dispatch_attempts: Mapped[int] = mapped_column(Integer, default=0)
    execution_attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_model_version_project"), UniqueConstraint("project_id", "name", "version_ref", name="uq_model_version_identity"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    name: Mapped[str] = mapped_column(String(255))
    version_ref: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JSON)


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_snapshot_project"), ForeignKeyConstraint(["dataset_id", "project_id"], ["datasets.id", "datasets.project_id"]))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dataset_id: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(80))
    item_count: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(64))


class SnapshotItem(Base):
    __tablename__ = "snapshot_items"
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("dataset_snapshots.id"), primary_key=True)
    sample_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    content: Mapped[dict] = mapped_column(JSON)


class PredictionSet(Base):
    __tablename__ = "prediction_sets"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_prediction_project"),
        UniqueConstraint("id", "snapshot_id", name="uq_prediction_snapshot"),
        UniqueConstraint("project_id", "snapshot_id", "model_version_id", "content_hash", name="uq_prediction_content"),
        ForeignKeyConstraint(["snapshot_id", "project_id"], ["dataset_snapshots.id", "dataset_snapshots.project_id"]),
        ForeignKeyConstraint(["model_version_id", "project_id"], ["model_versions.id", "model_versions.project_id"]),
        CheckConstraint("environment IN ('dev','staging','prod')", name="ck_prediction_environment"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    snapshot_id: Mapped[str] = mapped_column(String(64))
    model_version_id: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    content_hash: Mapped[str] = mapped_column(String(80))
    producer_manifest: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(String(16), default="partial")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        ForeignKeyConstraint(["set_id", "snapshot_id"], ["prediction_sets.id", "prediction_sets.snapshot_id"]),
        ForeignKeyConstraint(["snapshot_id", "sample_id"], ["snapshot_items.snapshot_id", "snapshot_items.sample_id"]),
    )
    set_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sample_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64))
    content: Mapped[dict] = mapped_column(JSON)


class TaskEvaluation(Base):
    __tablename__ = "task_evaluations"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_task_evaluation_project"),
        ForeignKeyConstraint(["prediction_set_id", "project_id"], ["prediction_sets.id", "prediction_sets.project_id"]),
        CheckConstraint("decision IS NULL OR decision IN ('pass','fail','review','inconclusive')", name="ck_task_decision"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','timed_out','uncertain')", name="ck_task_status"),
        CheckConstraint("(status IN ('queued','running') AND decision IS NULL) OR (status NOT IN ('queued','running') AND decision IS NOT NULL)", name="ck_task_terminal_decision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    prediction_set_id: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decision_reasons: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(64))


class MetricFact(Base):
    __tablename__ = "metric_facts"
    __table_args__ = (UniqueConstraint("task_evaluation_id", "definition_id", "definition_version", "scope", "scope_key", name="uq_metric_definition_scope"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_evaluation_id: Mapped[str] = mapped_column(ForeignKey("task_evaluations.id"))
    definition_id: Mapped[str] = mapped_column(String(128))
    definition_version: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str] = mapped_column(String(32))
    scope_key: Mapped[str] = mapped_column(Text)
    content: Mapped[dict] = mapped_column(JSON)


class TaskReceipt(Base):
    __tablename__ = "task_receipts"
    response_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    __table_args__ = (UniqueConstraint("project_id", "actor_id", "method", "path", "key", name="uq_task_receipt"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    actor_id: Mapped[str] = mapped_column(String(64))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(512))
    key: Mapped[str] = mapped_column(String(128))
    body_hash: Mapped[str] = mapped_column(String(80))
    resource_ref: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentRunEvaluation(Base):
    __tablename__ = "experiment_run_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "project_id"], ["experiment_runs.id", "experiment_runs.project_id"]),
        ForeignKeyConstraint(["task_evaluation_id", "project_id"], ["task_evaluations.id", "task_evaluations.project_id"]),
    )
    project_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    variant_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    task_evaluation_id: Mapped[str] = mapped_column(String(64))





class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_investigation_project"),
        CheckConstraint("environment IN ('dev','staging','prod')", name="ck_investigation_environment"),
        CheckConstraint("revision >= 1", name="ck_investigation_revision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    environment: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(JSON)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvestigationRevision(Base):
    __tablename__ = "investigation_revisions"
    __table_args__ = (
        UniqueConstraint("investigation_id", "revision", name="uq_investigation_revision"),
        ForeignKeyConstraint(["investigation_id", "project_id"], ["investigations.id", "investigations.project_id"]),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    state: Mapped[dict] = mapped_column(JSON)
    access_label: Mapped[dict] = mapped_column(JSON)
    author_kind: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_execution_project"),
        CheckConstraint("environment IN ('dev','staging','prod')", name="ck_execution_environment"),
        CheckConstraint("origin IN ('external_import','controlled_runner')", name="ck_execution_origin"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','timed_out','uncertain')", name="ck_imported_execution_status"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    environment: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(32), default="external_import", server_default="external_import")
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    manifest_hash: Mapped[str] = mapped_column(String(80))
    manifest_content: Mapped[str] = mapped_column(Text)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint("execution_id", "attempt_number", name="uq_execution_attempt_number"),
        ForeignKeyConstraint(["execution_id", "project_id"], ["executions.id", "executions.project_id"]),
        CheckConstraint("attempt_number >= 1", name="ck_execution_attempt_number"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    attempt_number: Mapped[int] = mapped_column(Integer)
    result_hash: Mapped[str] = mapped_column(String(80))
    result_content: Mapped[str] = mapped_column(Text)
    access_label: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionPolicyRevision(Base):
    __tablename__ = "execution_policy_revisions"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_execution_policy_version"),
                      CheckConstraint("version >= 1", name="ck_execution_policy_version"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(80))
    access_label: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Runner(Base):
    __tablename__ = "runners"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_runner_project"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    capabilities: Mapped[dict] = mapped_column(JSON)
    access_label: Mapped[dict] = mapped_column(JSON)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunnerCredential(Base):
    __tablename__ = "runner_credentials"
    __table_args__ = (ForeignKeyConstraint(["runner_id", "project_id"], ["runners.id", "runners.project_id"]),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    runner_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(String(64))
    prefix: Mapped[str] = mapped_column(String(32), index=True)
    hash: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganizationExecutionBudgetRevision(Base):
    __tablename__ = "organization_execution_budget_revisions"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_org_execution_budget_version"),
                      CheckConstraint("version >= 1", name="ck_org_execution_budget_version"))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(80))
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrganizationExecutionAccount(Base):
    __tablename__ = "organization_execution_accounts"
    __table_args__ = (CheckConstraint("reserved_units >= 0 AND spent_units >= 0", name="ck_org_execution_balance"),)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    reserved_units: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_units: Mapped[int] = mapped_column(BigInteger, default=0)


class ProjectExecutionAccount(Base):
    __tablename__ = "project_execution_accounts"
    __table_args__ = (CheckConstraint("reserved_units >= 0 AND spent_units >= 0", name="ck_project_execution_balance"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    reserved_units: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_units: Mapped[int] = mapped_column(BigInteger, default=0)


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"
    __table_args__ = (UniqueConstraint("id", "project_id", name="uq_execution_plan_project"),
                      ForeignKeyConstraint(["runner_id", "project_id"], ["runners.id", "runners.project_id"]))
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    environment: Mapped[str] = mapped_column(String(16))
    runner_id: Mapped[str] = mapped_column(String(64))
    policy_revision_id: Mapped[str] = mapped_column(ForeignKey("execution_policy_revisions.id"))
    organization_budget_revision_id: Mapped[str] = mapped_column(ForeignKey("organization_execution_budget_revisions.id"))
    manifest_content: Mapped[str] = mapped_column(Text)
    manifest_hash: Mapped[str] = mapped_column(String(80))
    access_label: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionReservation(Base):
    __tablename__ = "execution_reservations"
    __table_args__ = (
        ForeignKeyConstraint(["execution_id", "project_id"], ["executions.id", "executions.project_id"]),
        CheckConstraint("reserved_units >= 0 AND slots >= 1", name="ck_execution_reservation_amount"),
        CheckConstraint("state IN ('reserved','unknown','settled')", name="ck_execution_reservation_state"),
    )
    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    reserved_units: Mapped[int] = mapped_column(BigInteger)
    spent_units: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    slots: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    state: Mapped[str] = mapped_column(String(16), default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionLedgerEntry(Base):
    __tablename__ = "execution_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(["execution_id", "project_id"], ["executions.id", "executions.project_id"]),
        UniqueConstraint("execution_id", "event_key", name="uq_execution_ledger_event"),
        CheckConstraint("kind IN ('reserve','settle','release','adjust') AND amount_units >= 0 AND amount_units <= 100000000000000000", name="ck_execution_ledger_kind"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(String(64))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    attempt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    period: Mapped[str] = mapped_column(String(7))
    kind: Mapped[str] = mapped_column(String(16))
    event_key: Mapped[str] = mapped_column(String(128))
    amount_units: Mapped[int] = mapped_column(BigInteger)  # 10^-8 USD; never a float column
    measurement_source: Mapped[str] = mapped_column(String(255))
    pricing_version: Mapped[str] = mapped_column(String(128))
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExecutionSchedule(Base):
    __tablename__ = "execution_schedules"
    __table_args__ = (ForeignKeyConstraint(["execution_id", "project_id"], ["executions.id", "executions.project_id"]),
                      ForeignKeyConstraint(["plan_id", "project_id"], ["execution_plans.id", "execution_plans.project_id"]))
    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64))
    plan_id: Mapped[str] = mapped_column(String(64))
    actor_context: Mapped[dict] = mapped_column(JSON)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

from app.domain.tasks.immutability import register as _register_task_immutability
_register_task_immutability(Base.metadata)
