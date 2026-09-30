"""Add project Quality Gate configuration without changing existing tables."""
from alembic import op
import sqlalchemy as sa

revision = "0009_quality_gate_configs"
down_revision = "0008_export_jobs_file_size_bytes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_gate_configs",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("min_score", sa.Float(), nullable=False),
        sa.Column("max_ungrounded_rate", sa.Float(), nullable=False),
        sa.Column("max_avg_cost_usd", sa.Float(), nullable=False),
        sa.Column("max_p95_ms", sa.Integer(), nullable=False),
        sa.Column("require_zero_critical", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("quality_gate_configs")
