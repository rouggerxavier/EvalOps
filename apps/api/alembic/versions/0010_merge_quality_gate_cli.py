"""Join Quality Gate and nullable judge-cost migrations without changing data."""

revision = "0010_merge_quality_gate_cli"
down_revision = ("0009_quality_gate_configs", "0009_eval_cost_nullable")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
