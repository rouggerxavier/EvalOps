"""Evaluation cost may be unknown (local CLI judge): NULL, never a fake 0.

Revision ID: 0009_eval_cost_nullable
Revises: 0008_export_jobs_file_size_bytes
Create Date: 2026-11-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009_eval_cost_nullable"
down_revision: Union[str, Sequence[str], None] = "0008_export_jobs_file_size_bytes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("evaluation_runs", "evaluation_scores")
_COST = sa.Numeric(12, 6)


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("cost_usd", existing_type=_COST, nullable=True)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"UPDATE {table} SET cost_usd = 0 WHERE cost_usd IS NULL")
        with op.batch_alter_table(table) as batch:
            batch.alter_column("cost_usd", existing_type=_COST, nullable=False)
