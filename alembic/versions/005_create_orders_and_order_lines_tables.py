"""create orders and order_lines tables

Revision ID: 005
Revises: 004
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("guest_email", sa.String(254), nullable=True),
        sa.Column("shipping_address", JSONB(), nullable=False),
        sa.Column("shipping_method_id", sa.Uuid(), nullable=False),
        sa.Column("shipping_cost_minor", sa.Integer(), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Uuid(), nullable=True),
        sa.Column("notification_status", sa.String(20), nullable=True),
        sa.Column("payment_intent_id", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_orders_tenant_reference"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_orders_tenant_idempotency_key",
        ),
        sa.CheckConstraint(
            "customer_id IS NOT NULL OR guest_email IS NOT NULL",
            name="ck_orders_customer_or_guest",
        ),
    )
    op.create_index("idx_orders_tenant_status", "orders", ["tenant_id", "status"])
    op.create_index(
        "idx_orders_guest_email",
        "orders",
        ["guest_email"],
        postgresql_where=sa.text("guest_email IS NOT NULL"),
    )

    op.create_table(
        "order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("variant_label", sa.String(200), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.CheckConstraint("quantity >= 1", name="ck_order_lines_quantity"),
        sa.CheckConstraint("unit_price_minor >= 0", name="ck_order_lines_unit_price"),
    )
    op.create_index("idx_order_lines_order_id", "order_lines", ["order_id"])


def downgrade() -> None:
    op.drop_index("idx_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index("idx_orders_guest_email", table_name="orders")
    op.drop_index("idx_orders_tenant_status", table_name="orders")
    op.drop_table("orders")
