"""composite index on evaluation_runs(trace_id, created_at desc).

Revision ID: 0007_eval_runs_trace_created
Revises: 0006_prompt_ref_index
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0007_eval_runs_trace_created"
down_revision: Union[str, Sequence[str], None] = "0006_prompt_ref_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_evaluation_runs_trace_created "
            "ON evaluation_runs (trace_id, created_at DESC)"
        )
    else:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_evaluation_runs_trace_created "
            "ON evaluation_runs (trace_id, created_at)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_evaluation_runs_trace_created")
