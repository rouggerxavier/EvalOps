"""runner_leases

Revision ID: 0021_runner_leases
Revises: 0019_execution_ledger
Create Date: 2026-11-12 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021_runner_leases'
down_revision: Union[str, Sequence[str], None] = '0019_execution_ledger'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMMUTABLE = {
    "execution_leases": "execution_id,project_id,attempt_id,runner_id,credential_id,claim_key,claimed_at",
    "execution_late_reports": "id,execution_id,project_id,attempt_id,reason,content,content_hash,created_at",
}


def upgrade() -> None:
    op.create_table('execution_leases',
    sa.Column('execution_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('attempt_id', sa.String(length=64), nullable=False),
    sa.Column('runner_id', sa.String(length=64), nullable=False),
    sa.Column('credential_id', sa.String(length=64), nullable=False),
    sa.Column('claim_key', sa.String(length=128), nullable=False),
    sa.Column('token_hash', sa.String(length=80), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('report_hash', sa.String(length=80), nullable=True),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("state IN ('active','completed','expired','lost')", name='ck_execution_lease_state'),
    sa.ForeignKeyConstraint(['credential_id'], ['runner_credentials.id'], ),
    sa.ForeignKeyConstraint(['execution_id', 'project_id'], ['executions.id', 'executions.project_id'], ),
    sa.ForeignKeyConstraint(['runner_id', 'project_id'], ['runners.id', 'runners.project_id'], ),
    sa.PrimaryKeyConstraint('execution_id'),
    sa.UniqueConstraint('attempt_id'),
    sa.UniqueConstraint('runner_id', 'claim_key', name='uq_execution_lease_claim')
    )
    with op.batch_alter_table('execution_leases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_leases_project_id'), ['project_id'], unique=False)

    op.create_table('execution_late_reports',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('execution_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('attempt_id', sa.String(length=64), nullable=False),
    sa.Column('reason', sa.String(length=64), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=80), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['execution_id', 'project_id'], ['executions.id', 'executions.project_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('attempt_id', 'content_hash', name='uq_execution_late_report')
    )
    with op.batch_alter_table('execution_late_reports', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_late_reports_execution_id'), ['execution_id'], unique=False)

    dialect = op.get_bind().dialect.name
    for table, names in IMMUTABLE.items():
        if dialect == "sqlite":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
            op.execute(f"CREATE TRIGGER immutable_{table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
        elif dialect == "postgresql":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")
            op.execute(f"CREATE TRIGGER immutable_{table}_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")
    if dialect == "sqlite":
        op.execute("CREATE TRIGGER immutable_execution_lease_closed BEFORE UPDATE ON execution_leases WHEN (OLD.state <> 'active') BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
    elif dialect == "postgresql":
        op.execute("CREATE TRIGGER immutable_execution_lease_closed BEFORE UPDATE ON execution_leases FOR EACH ROW WHEN (OLD.state <> 'active') EXECUTE FUNCTION evalops_immutable_task_row()")


def downgrade() -> None:
    # Leases and late reports are spend/uncertainty evidence: never drop them to unblock a rollback.
    for table in ("execution_leases", "execution_late_reports"):
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("runner_leases_downgrade_requires_empty_tables")
    with op.batch_alter_table('execution_late_reports', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_late_reports_execution_id'))

    op.drop_table('execution_late_reports')
    with op.batch_alter_table('execution_leases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_leases_project_id'))

    op.drop_table('execution_leases')
