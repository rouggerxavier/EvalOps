"""execution_imports

Revision ID: 0016_execution_imports
Revises: 0015_investigations
Create Date: 2026-11-10 17:38:08.439308

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016_execution_imports'
down_revision: Union[str, Sequence[str], None] = '0015_investigations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('executions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('mode', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('manifest_hash', sa.String(length=80), nullable=False),
    sa.Column('manifest_content', sa.Text(), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("environment IN ('dev','staging','prod')", name='ck_execution_environment'),
    sa.CheckConstraint("status IN ('succeeded','failed','cancelled','timed_out','uncertain')", name='ck_imported_execution_status'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_execution_project')
    )
    with op.batch_alter_table('executions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_executions_project_id'), ['project_id'], unique=False)

    op.create_table('execution_attempts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('execution_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('attempt_number', sa.Integer(), nullable=False),
    sa.Column('result_hash', sa.String(length=80), nullable=False),
    sa.Column('result_content', sa.Text(), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('attempt_number >= 1', name='ck_execution_attempt_number'),
    sa.ForeignKeyConstraint(['execution_id', 'project_id'], ['executions.id', 'executions.project_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('execution_id', 'attempt_number', name='uq_execution_attempt_number')
    )
    columns = {
        "executions": "id,project_id,environment,mode,status,manifest_hash,manifest_content,created_by,created_at",
        "execution_attempts": "id,execution_id,project_id,environment,attempt_number,result_hash,result_content,created_at",
    }
    for table, names in columns.items():
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
        elif op.get_bind().dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM executions")).scalar():
        raise RuntimeError("execution_imports_downgrade_requires_empty_tables")
    op.drop_table('execution_attempts')
    with op.batch_alter_table('executions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_executions_project_id'))

    op.drop_table('executions')
