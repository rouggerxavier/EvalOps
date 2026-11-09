"""Revoke personal JWT sessions when a user changes their password.

Revision ID: 0013_user_credential_version
Revises: 0012_evaluation_sampling
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_user_credential_version"
down_revision = "0012_evaluation_sampling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("credential_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "credential_version")
