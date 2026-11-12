"""execution_ledger

Revision ID: 0019_execution_ledger
Revises: 0018_password_resets
Create Date: 2026-11-10 18:25:22.238701

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019_execution_ledger'
down_revision: Union[str, Sequence[str], None] = '0018_password_resets'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('organization_execution_accounts',
    sa.Column('organization_id', sa.String(length=64), nullable=False),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('reserved_units', sa.BigInteger(), nullable=False),
    sa.Column('spent_units', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('reserved_units >= 0 AND spent_units >= 0', name='ck_org_execution_balance'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('organization_id', 'period')
    )
    op.create_table('organization_execution_budget_revisions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('organization_id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('content_hash', sa.String(length=80), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('version >= 1', name='ck_org_execution_budget_version'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'version', name='uq_org_execution_budget_version')
    )
    with op.batch_alter_table('organization_execution_budget_revisions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organization_execution_budget_revisions_organization_id'), ['organization_id'], unique=False)

    op.create_table('project_execution_accounts',
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('reserved_units', sa.BigInteger(), nullable=False),
    sa.Column('spent_units', sa.BigInteger(), nullable=False),
    sa.CheckConstraint('reserved_units >= 0 AND spent_units >= 0', name='ck_project_execution_balance'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('project_id', 'period')
    )
    op.create_table('execution_ledger_entries',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('execution_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('organization_id', sa.String(length=64), nullable=False),
    sa.Column('attempt_id', sa.String(length=64), nullable=True),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('event_key', sa.String(length=128), nullable=False),
    sa.Column('amount_units', sa.BigInteger(), nullable=False),
    sa.Column('measurement_source', sa.String(length=255), nullable=False),
    sa.Column('pricing_version', sa.String(length=128), nullable=False),
    sa.Column('actor_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('reserve','settle','release','adjust') AND amount_units >= 0 AND amount_units <= 100000000000000000", name='ck_execution_ledger_kind'),
    sa.ForeignKeyConstraint(['execution_id', 'project_id'], ['executions.id', 'executions.project_id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('execution_id', 'event_key', name='uq_execution_ledger_event')
    )
    with op.batch_alter_table('execution_ledger_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_ledger_entries_execution_id'), ['execution_id'], unique=False)

    op.create_table('execution_plans',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('runner_id', sa.String(length=64), nullable=False),
    sa.Column('policy_revision_id', sa.String(length=64), nullable=False),
    sa.Column('organization_budget_revision_id', sa.String(length=64), nullable=False),
    sa.Column('manifest_content', sa.Text(), nullable=False),
    sa.Column('manifest_hash', sa.String(length=80), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_budget_revision_id'], ['organization_execution_budget_revisions.id'], ),
    sa.ForeignKeyConstraint(['policy_revision_id'], ['execution_policy_revisions.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['runner_id', 'project_id'], ['runners.id', 'runners.project_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_execution_plan_project')
    )
    with op.batch_alter_table('execution_plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_plans_project_id'), ['project_id'], unique=False)

    op.create_table('execution_reservations',
    sa.Column('execution_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('organization_id', sa.String(length=64), nullable=False),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('reserved_units', sa.BigInteger(), nullable=False),
    sa.Column('spent_units', sa.BigInteger(), nullable=True),
    sa.Column('slots', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("state IN ('reserved','unknown','settled')", name='ck_execution_reservation_state'),
    sa.CheckConstraint('reserved_units >= 0 AND slots >= 1', name='ck_execution_reservation_amount'),
    sa.ForeignKeyConstraint(['execution_id', 'project_id'], ['executions.id', 'executions.project_id'], ),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('execution_id')
    )
    with op.batch_alter_table('execution_reservations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_reservations_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_execution_reservations_project_id'), ['project_id'], unique=False)

    op.create_table('execution_schedules',
    sa.Column('execution_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('plan_id', sa.String(length=64), nullable=False),
    sa.Column('actor_context', sa.JSON(), nullable=False),
    sa.Column('cancel_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['execution_id', 'project_id'], ['executions.id', 'executions.project_id'], ),
    sa.ForeignKeyConstraint(['plan_id', 'project_id'], ['execution_plans.id', 'execution_plans.project_id'], ),
    sa.PrimaryKeyConstraint('execution_id')
    )
    op.execute('DROP TRIGGER IF EXISTS immutable_executions' + (' ON executions' if op.get_bind().dialect.name == 'postgresql' else ''))
    with op.batch_alter_table('executions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origin', sa.String(length=32), server_default='external_import', nullable=False))
        batch_op.drop_constraint('ck_imported_execution_status', type_='check')
        batch_op.create_check_constraint('ck_imported_execution_status', "status IN ('queued','running','succeeded','failed','cancelled','timed_out','uncertain')")
        batch_op.create_check_constraint('ck_execution_origin', "origin IN ('external_import','controlled_runner')")

    columns = {
        "organization_execution_budget_revisions": "id,organization_id,version,content,content_hash,created_by,created_at",
        "execution_plans": "id,project_id,environment,runner_id,policy_revision_id,organization_budget_revision_id,manifest_content,manifest_hash,created_by,created_at",
        "execution_ledger_entries": "id,execution_id,project_id,organization_id,attempt_id,period,kind,event_key,amount_units,measurement_source,pricing_version,actor_id,created_at",
        "execution_schedules": "execution_id,project_id,plan_id,actor_context,created_at",
        "executions": "id,project_id,environment,origin,mode,manifest_hash,manifest_content,created_by,created_at",
    }
    for table, names in columns.items():
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
        elif op.get_bind().dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")
    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER immutable_execution_terminal_status BEFORE UPDATE OF status ON executions WHEN (OLD.status NOT IN ('queued','running')) BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
        op.execute("CREATE TRIGGER immutable_execution_ledger_delete BEFORE DELETE ON execution_ledger_entries BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE TRIGGER immutable_execution_terminal_status BEFORE UPDATE OF status ON executions FOR EACH ROW WHEN (OLD.status NOT IN ('queued','running')) EXECUTE FUNCTION evalops_immutable_task_row()")
        op.execute("CREATE TRIGGER immutable_execution_ledger_delete BEFORE DELETE ON execution_ledger_entries FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")


def downgrade() -> None:
    for table in ("execution_schedules", "execution_reservations", "execution_plans", "execution_ledger_entries", "organization_execution_budget_revisions", "organization_execution_accounts", "project_execution_accounts"):
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("execution_ledger_downgrade_requires_empty_tables")
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM executions WHERE origin='controlled_runner' OR status IN ('queued','running')")).scalar():
        raise RuntimeError("execution_ledger_downgrade_requires_empty_tables")
    suffix = " ON executions" if op.get_bind().dialect.name == "postgresql" else ""
    op.execute("DROP TRIGGER IF EXISTS immutable_executions" + suffix)
    op.execute("DROP TRIGGER IF EXISTS immutable_execution_terminal_status" + suffix)
    with op.batch_alter_table('executions', schema=None) as batch_op:
        batch_op.drop_constraint('ck_execution_origin', type_='check')
        batch_op.drop_constraint('ck_imported_execution_status', type_='check')
        batch_op.create_check_constraint('ck_imported_execution_status', "status IN ('succeeded','failed','cancelled','timed_out','uncertain')")
        batch_op.drop_column('origin')
    names = "id,project_id,environment,mode,status,manifest_hash,manifest_content,created_by,created_at"
    if op.get_bind().dialect.name == "sqlite":
        op.execute(f"CREATE TRIGGER immutable_executions BEFORE UPDATE OF {names} ON executions BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute(f"CREATE TRIGGER immutable_executions BEFORE UPDATE OF {names} ON executions FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")
    op.drop_table('execution_schedules')
    with op.batch_alter_table('execution_reservations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_reservations_project_id'))
        batch_op.drop_index(batch_op.f('ix_execution_reservations_organization_id'))

    op.drop_table('execution_reservations')
    with op.batch_alter_table('execution_plans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_plans_project_id'))

    op.drop_table('execution_plans')
    with op.batch_alter_table('execution_ledger_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_ledger_entries_execution_id'))

    op.drop_table('execution_ledger_entries')
    op.drop_table('project_execution_accounts')
    with op.batch_alter_table('organization_execution_budget_revisions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organization_execution_budget_revisions_organization_id'))

    op.drop_table('organization_execution_budget_revisions')
    op.drop_table('organization_execution_accounts')
