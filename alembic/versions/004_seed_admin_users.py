"""Seed admin test users

Revision ID: 004
Revises: 003
Create Date: 2026-04-12

Seed data for testing. Passwords are bcrypt-hashed "ValidPass123!".
TOTP secret: JBSWY3DPEHPK3PXP (for owner and admin roles).

"""

from collections.abc import Sequence
from datetime import datetime, timezone

import bcrypt
import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
TOTP_SECRET = "JBSWY3DPEHPK3PXP"

# Pre-computed bcrypt hash for "ValidPass123!" (cost factor 12)
# Generated at migration time — safe for test environments
_PASSWORD = "ValidPass123!"

TEST_USERS = [
    {
        "id": "20000000-0000-0000-0000-000000000001",
        "email": "owner@example.com",
        "role": "merchant_owner",
        "totp_secret": TOTP_SECRET,
    },
    {
        "id": "20000000-0000-0000-0000-000000000002",
        "email": "admin@example.com",
        "role": "merchant_admin",
        "totp_secret": TOTP_SECRET,
    },
    {
        "id": "20000000-0000-0000-0000-000000000003",
        "email": "viewer@example.com",
        "role": "merchant_viewer",
        "totp_secret": None,
    },
    {
        "id": "20000000-0000-0000-0000-000000000004",
        "email": "support@example.com",
        "role": "merchant_support",
        "totp_secret": None,
    },
]


def upgrade() -> None:
    now = datetime.now(timezone.utc).isoformat()
    password_hash = bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt(rounds=12)).decode()

    for user in TEST_USERS:
        op.execute(
            sa.text(
                """
                INSERT INTO admin_users
                    (id, tenant_id, email, password_hash, role,
                     totp_secret, is_active, created_at, updated_at)
                VALUES
                 (CAST(:id AS uuid), CAST(:tenant_id AS uuid), :email, :password_hash, :role,
                      :totp_secret, true, CAST(:now AS timestamptz), CAST(:now AS timestamptz))
                ON CONFLICT DO NOTHING
                """
            ).bindparams(
                id=user["id"],
                tenant_id=DEFAULT_TENANT_ID,
                email=user["email"],
                password_hash=password_hash,
                role=user["role"],
                totp_secret=user["totp_secret"],
                now=now,
            )
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM admin_users WHERE tenant_id = :tenant_id").bindparams(
            tenant_id=DEFAULT_TENANT_ID
        )
    )
