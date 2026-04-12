"""Create admin_users table

Revision ID: 003
Revises: 002
Create Date: 2026-04-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("totp_secret", sa.String(100), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_admin_users_tenant_email"),
        sa.CheckConstraint(
            "role IN ('merchant_owner', 'merchant_admin', 'merchant_viewer', 'merchant_support')",
            name="ck_admin_users_role",
        ),
    )


def downgrade() -> None:
    op.drop_table("admin_users")
