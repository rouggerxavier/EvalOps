"""Protect execution attempt evidence from deletion.

Revision ID: 0023_attempt_delete_guard
Revises: 0022_organization_invitations
"""
from alembic import op

revision = "0023_attempt_delete_guard"
down_revision = "0022_organization_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("CREATE TRIGGER immutable_execution_attempts_delete BEFORE DELETE ON execution_attempts BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
    elif dialect == "postgresql":
        op.execute("CREATE TRIGGER immutable_execution_attempts_delete BEFORE DELETE ON execution_attempts FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")


def downgrade() -> None:
    suffix = " ON execution_attempts" if op.get_bind().dialect.name == "postgresql" else ""
    op.execute("DROP TRIGGER IF EXISTS immutable_execution_attempts_delete" + suffix)
