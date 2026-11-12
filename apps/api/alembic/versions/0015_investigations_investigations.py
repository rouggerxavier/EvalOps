"""investigations

Revision ID: 0015_investigations
Revises: 0014_task_foundations
Create Date: 2026-11-10 16:55:32.231018

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015_investigations'
down_revision: Union[str, Sequence[str], None] = '0014_task_foundations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('task_receipts', sa.Column('response_snapshot', sa.JSON(), nullable=True))
    op.create_table('investigations',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("environment IN ('dev','staging','prod')", name='ck_investigation_environment'),
    sa.CheckConstraint('revision >= 1', name='ck_investigation_revision'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_investigation_project')
    )
    with op.batch_alter_table('investigations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_investigations_project_id'), ['project_id'], unique=False)

    op.create_table('investigation_revisions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('investigation_id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('author_kind', sa.String(length=16), nullable=False),
    sa.Column('author_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['investigation_id', 'project_id'], ['investigations.id', 'investigations.project_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('investigation_id', 'revision', name='uq_investigation_revision')
    )

    if op.get_bind().dialect.name == "sqlite":
        op.execute("CREATE TRIGGER immutable_investigation_revisions BEFORE UPDATE OF id,investigation_id,project_id,environment,revision,state,access_label,author_kind,author_id,created_at ON investigation_revisions BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE TRIGGER immutable_investigation_revisions BEFORE UPDATE OF id,investigation_id,project_id,environment,revision,state,access_label,author_kind,author_id,created_at ON investigation_revisions FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()")


def downgrade() -> None:
    if (op.get_bind().execute(sa.text("SELECT COUNT(*) FROM investigations")).scalar()
            or op.get_bind().execute(sa.text("SELECT COUNT(*) FROM task_receipts WHERE response_snapshot IS NOT NULL")).scalar()):
        raise RuntimeError("investigations_downgrade_requires_empty_tables")
    op.drop_table('investigation_revisions')
    with op.batch_alter_table('investigations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_investigations_project_id'))

    op.drop_table('investigations')
    op.drop_column('task_receipts', 'response_snapshot')
