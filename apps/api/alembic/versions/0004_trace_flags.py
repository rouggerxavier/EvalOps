"""add trace flags table.

Revision ID: 0004_trace_flags
Revises: 0003_notifications
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_trace_flags"
down_revision: Union[str, Sequence[str], None] = "0003_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trace_flags",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trace_flags_trace_id", "trace_flags", ["trace_id"])
    op.create_index("ix_trace_flags_org_id", "trace_flags", ["org_id"])
    op.create_index("ix_trace_flags_user_id", "trace_flags", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_trace_flags_user_id", table_name="trace_flags")
    op.drop_index("ix_trace_flags_org_id", table_name="trace_flags")
    op.drop_index("ix_trace_flags_trace_id", table_name="trace_flags")
    op.drop_table("trace_flags")
