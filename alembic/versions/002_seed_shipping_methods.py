"""Seed shipping methods for default tenant

Revision ID: 002
Revises: 001
Create Date: 2026-04-12

"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
STANDARD_ID = "10000000-0000-0000-0000-000000000001"
EXPRESS_ID = "10000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    now = datetime.now(timezone.utc).isoformat()
    op.execute(
        sa.text(
            """
            INSERT INTO shipping_methods
                (id, tenant_id, name, description, cost_minor,
                 estimated_days_min, estimated_days_max, is_active,
                 created_at, updated_at)
            VALUES
                (:id1, :tenant_id, 'Standard Shipping',
                 'Delivery in 3-5 business days', 599, 3, 5, true, :now, :now),
                (:id2, :tenant_id, 'Express Shipping',
                 'Delivery in 1-2 business days', 1499, 1, 2, true, :now, :now)
            ON CONFLICT DO NOTHING
            """
        ).bindparams(
            id1=STANDARD_ID,
            id2=EXPRESS_ID,
            tenant_id=DEFAULT_TENANT_ID,
            now=now,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM shipping_methods WHERE tenant_id = :tenant_id").bindparams(
            tenant_id=DEFAULT_TENANT_ID
        )
    )
