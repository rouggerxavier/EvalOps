"""export_jobs.file_size_bytes column.

Revision ID: 0008_export_jobs_file_size_bytes
Revises: 0007_eval_runs_trace_created
Create Date: 2026-05-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_export_jobs_file_size_bytes"
down_revision: Union[str, Sequence[str], None] = "0007_eval_runs_trace_created"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "export_jobs",
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("export_jobs", "file_size_bytes")
