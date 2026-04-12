"""Create guest_sessions and shipping_methods tables

Revision ID: 001
Revises:
Create Date: 2026-04-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guest_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_guest_sessions_token", "guest_sessions", ["token"], unique=True)
    op.create_index("idx_guest_sessions_expires", "guest_sessions", ["expires_at"])

    op.create_table(
        "shipping_methods",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("cost_minor", sa.Integer(), nullable=False),
        sa.Column("estimated_days_min", sa.Integer(), nullable=True),
        sa.Column("estimated_days_max", sa.Integer(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_shipping_methods_tenant_name"),
        sa.CheckConstraint("cost_minor >= 0", name="ck_shipping_methods_cost_minor"),
    )


def downgrade() -> None:
    op.drop_table("shipping_methods")
    op.drop_table("guest_sessions")
