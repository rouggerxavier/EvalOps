"""Organization invitations and serialized membership management.

Revision ID: 0022_organization_invitations
Revises: 0021_runner_leases
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_organization_invitations"
down_revision = "0021_runner_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("membership_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("invited_by_user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('member', 'viewer')", name="ck_organization_invitations_role"),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed', 'accepted', 'revoked')",
                           name="ck_organization_invitations_status"),
    )
    op.create_index("ix_organization_invitations_listing", "organization_invitations", ["organization_id", "created_at", "id"])
    op.create_index("ix_organization_invitations_email", "organization_invitations", ["organization_id", "email"])


def downgrade() -> None:
    op.drop_table("organization_invitations")
    op.drop_column("organizations", "membership_version")
