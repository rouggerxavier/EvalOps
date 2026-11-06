"""usage_counters.replay_cost_usd column.

Revision ID: 0011_usage_replay_cost
Revises: 0010_merge_quality_gate_cli
Create Date: 2026-11-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_usage_replay_cost"
down_revision: Union[str, Sequence[str], None] = "0010_merge_quality_gate_cli"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usage_counters",
        sa.Column("replay_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("usage_counters", "replay_cost_usd")
