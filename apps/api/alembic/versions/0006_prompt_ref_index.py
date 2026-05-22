"""add index on traces.metadata->>'prompt_ref' (Postgres only).

Revision ID: 0006_prompt_ref_index
Revises: 0005_project_default_environment
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0006_prompt_ref_index"
down_revision: Union[str, Sequence[str], None] = "0005_project_default_environment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_traces_metadata_prompt_ref "
        "ON traces (((metadata->>'prompt_ref')))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_traces_metadata_prompt_version_ref "
        "ON traces (((metadata->>'prompt_version_ref')))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_traces_metadata_prompt_ref")
    op.execute("DROP INDEX IF EXISTS ix_traces_metadata_prompt_version_ref")
