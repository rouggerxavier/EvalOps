"""runner_policy

Revision ID: 0017_runner_policy
Revises: 0016_execution_imports
Create Date: 2026-11-10 17:52:29.511835

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017_runner_policy'
down_revision: Union[str, Sequence[str], None] = '0016_execution_imports'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('execution_policy_revisions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('content_hash', sa.String(length=80), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.CheckConstraint('version >= 1', name='ck_execution_policy_version'),
    sa.UniqueConstraint('project_id', 'version', name='uq_execution_policy_version')
    )
    with op.batch_alter_table('execution_policy_revisions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_execution_policy_revisions_project_id'), ['project_id'], unique=False)

    op.create_table('runners',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('owner_user_id', sa.String(length=64), nullable=False),
    sa.Column('capabilities', sa.JSON(), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_runner_project')
    )
    with op.batch_alter_table('runners', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_runners_project_id'), ['project_id'], unique=False)

    op.create_table('runner_credentials',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('runner_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('prefix', sa.String(length=32), nullable=False),
    sa.Column('hash', sa.String(length=512), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['runner_id', 'project_id'], ['runners.id', 'runners.project_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('runner_credentials', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_runner_credentials_prefix'), ['prefix'], unique=False)
        batch_op.create_index(batch_op.f('ix_runner_credentials_runner_id'), ['runner_id'], unique=False)

    columns = {
        "execution_policy_revisions": "id,project_id,version,content,content_hash,created_by,created_at",
        "runners": "id,project_id,name,owner_user_id,capabilities,created_at",
    }
    for table, names in columns.items():
        if op.get_bind().dialect.name == "sqlite":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
        elif op.get_bind().dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {names} ON {table} FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")


def downgrade() -> None:
    if (op.get_bind().execute(sa.text("SELECT COUNT(*) FROM execution_policy_revisions")).scalar()
            or op.get_bind().execute(sa.text("SELECT COUNT(*) FROM runners")).scalar()):
        raise RuntimeError("runner_policy_downgrade_requires_empty_tables")
    with op.batch_alter_table('runner_credentials', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_runner_credentials_runner_id'))
        batch_op.drop_index(batch_op.f('ix_runner_credentials_prefix'))

    op.drop_table('runner_credentials')
    with op.batch_alter_table('runners', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_runners_project_id'))

    op.drop_table('runners')
    with op.batch_alter_table('execution_policy_revisions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_execution_policy_revisions_project_id'))

    op.drop_table('execution_policy_revisions')
