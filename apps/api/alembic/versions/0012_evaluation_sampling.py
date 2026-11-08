"""Opt-in evaluation sampling and durable dispatch markers.

Revision ID: 0012_evaluation_sampling
Revises: 0011_usage_replay_cost
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_evaluation_sampling"
down_revision = "0011_usage_replay_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_sampling_configs",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rubric_id", sa.String(64), nullable=True),
        sa.Column("rubric_version", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("percentage >= 0 AND percentage <= 100", name="ck_sampling_percentage"),
        sa.ForeignKeyConstraint(["rubric_id", "rubric_version"], ["rubric_versions.rubric_id", "rubric_versions.version"], ondelete="RESTRICT"),
    )
    op.create_table(
        "evaluation_sampling_jobs",
        sa.Column("trace_id", sa.String(64), sa.ForeignKey("traces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rubric_id", sa.String(64), nullable=False),
        sa.Column("rubric_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64), nullable=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("evaluation_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False),
        sa.Column("execution_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rubric_id", "rubric_version"], ["rubric_versions.rubric_id", "rubric_versions.version"], ondelete="RESTRICT"),
    )
    op.create_index("ix_evaluation_sampling_jobs_project_id", "evaluation_sampling_jobs", ["project_id"])
    op.create_index("ix_sampling_jobs_dispatch", "evaluation_sampling_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("evaluation_sampling_jobs")
    op.drop_table("evaluation_sampling_configs")
