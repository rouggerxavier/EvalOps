"""add project default environment.

Revision ID: 0005_project_default_environment
Revises: 0004_trace_flags
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_project_default_environment"
down_revision: Union[str, Sequence[str], None] = "0004_trace_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("default_environment", sa.String(length=16), nullable=False, server_default="prod"),
    )


def downgrade() -> None:
    op.drop_column("projects", "default_environment")
