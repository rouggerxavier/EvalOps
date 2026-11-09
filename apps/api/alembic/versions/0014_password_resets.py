"""Single-use, hash-only password recovery requests.

Revision ID: 0014_password_resets
Revises: 0013_user_credential_version
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_password_resets"
down_revision = "0013_user_credential_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False, unique=True),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])


def downgrade() -> None:
    op.drop_table("password_resets")
