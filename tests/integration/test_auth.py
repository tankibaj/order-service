"""
Integration tests for admin authentication endpoints.

TS scenarios covered:
  TS-001-039 — Viewer/support login returns fully authenticated JWT
  TS-001-040 — Owner/admin login returns pre-MFA JWT
  TS-001-041 — Valid TOTP code upgrades JWT to fully authenticated
  TS-001-042 — Invalid TOTP code is rejected
  TS-001-043 — Wrong password returns generic 401
  TS-001-044 — Non-existent email returns same generic 401
  TS-001-045 — Pre-MFA JWT cannot access admin endpoints
"""

import uuid
from datetime import datetime, timezone

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.admin_user import AdminUserModel
from src.services.password_service import hash_password
from tests.conftest import TEST_TENANT_ID

TENANT_HEADER = {"X-Tenant-ID": str(TEST_TENANT_ID)}
TOTP_SECRET = "JBSWY3DPEHPK3PXP"

# ── Fixtures ──────────────────────────────────────────────────────────────────


async def _create_user(
    db: AsyncSession,
    email: str,
    role: str,
    totp_secret: str | None = None,
    password: str = "ValidPass123!",
) -> AdminUserModel:
    """Helper: create an admin user in the test database."""
    user = AdminUserModel(
        tenant_id=TEST_TENANT_ID,
        email=email,
        password_hash=hash_password(password),
        role=role,
        totp_secret=totp_secret,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def viewer_user(db_session: AsyncSession) -> AdminUserModel:
    return await _create_user(
        db_session,
        email=f"viewer-{uuid.uuid4()}@example.com",
        role="merchant_viewer",
    )


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> AdminUserModel:
    return await _create_user(
        db_session,
        email=f"owner-{uuid.uuid4()}@example.com",
        role="merchant_owner",
        totp_secret=TOTP_SECRET,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_ts_001_039_viewer_login_returns_fully_authenticated_jwt(
    client: AsyncClient, viewer_user: AdminUserModel
) -> None:
    """TS-001-039: Viewer/support login returns JWT NOT flagged as pre-MFA."""
    response = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": viewer_user.email, "password": "ValidPass123!"},
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert "access_token" in body
    assert body["token_type"] == "Bearer"
    assert "expires_in" in body

    # mfa_required should be False (or absent) for viewer
    assert body.get("mfa_required") is False or body.get("mfa_required") is None

    # Token should allow access to GET /orders (returns 200 with empty list)
    orders_resp = await client.get(
        "/orders",
        headers={**TENANT_HEADER, "Authorization": f"Bearer {body['access_token']}"},
    )
    assert orders_resp.status_code == 200, (
        f"Viewer JWT rejected from /orders with {orders_resp.status_code}"
    )


async def test_ts_001_040_owner_login_returns_pre_mfa_jwt(
    client: AsyncClient, owner_user: AdminUserModel
) -> None:
    """TS-001-040: Owner login returns JWT with mfa_required=True."""
    response = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": owner_user.email, "password": "ValidPass123!"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("mfa_required") is True, f"Expected mfa_required=True, got {body}"

    # Pre-MFA JWT should be rejected from GET /orders with 403
    orders_resp = await client.get(
        "/orders",
        headers={**TENANT_HEADER, "Authorization": f"Bearer {body['access_token']}"},
    )
    assert orders_resp.status_code == 403, (
        f"Pre-MFA JWT should be rejected from /orders with 403, got {orders_resp.status_code}"
    )


async def test_ts_001_041_valid_totp_upgrades_jwt(
    client: AsyncClient, owner_user: AdminUserModel
) -> None:
    """TS-001-041: Valid TOTP code upgrades pre-MFA JWT to fully authenticated."""
    # Step 1: Login to get pre-MFA JWT
    login_resp = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": owner_user.email, "password": "ValidPass123!"},
    )
    assert login_resp.status_code == 200
    pre_mfa_token = login_resp.json()["access_token"]

    # Step 2: Verify TOTP with valid code
    valid_code = pyotp.TOTP(TOTP_SECRET).now()
    mfa_resp = await client.post(
        "/auth/mfa/verify",
        headers={**TENANT_HEADER, "Authorization": f"Bearer {pre_mfa_token}"},
        json={"code": valid_code},
    )
    assert mfa_resp.status_code == 200, mfa_resp.text
    mfa_body = mfa_resp.json()
    assert "access_token" in mfa_body

    # Step 3: Fully-authenticated JWT must allow GET /orders
    orders_resp = await client.get(
        "/orders",
        headers={
            **TENANT_HEADER,
            "Authorization": f"Bearer {mfa_body['access_token']}",
        },
    )
    assert orders_resp.status_code == 200, (
        f"Fully-authenticated JWT rejected from /orders with {orders_resp.status_code}"
    )


async def test_ts_001_042_invalid_totp_rejected(
    client: AsyncClient, owner_user: AdminUserModel
) -> None:
    """TS-001-042: Invalid TOTP code returns 401, JWT NOT upgraded."""
    # Login to get pre-MFA JWT
    login_resp = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": owner_user.email, "password": "ValidPass123!"},
    )
    assert login_resp.status_code == 200
    pre_mfa_token = login_resp.json()["access_token"]

    # Submit invalid TOTP code
    mfa_resp = await client.post(
        "/auth/mfa/verify",
        headers={**TENANT_HEADER, "Authorization": f"Bearer {pre_mfa_token}"},
        json={"code": "000000"},
    )
    assert mfa_resp.status_code in (401, 403), (
        f"Expected 401 or 403 for invalid TOTP, got {mfa_resp.status_code}"
    )

    # Pre-MFA token still cannot access /orders
    orders_resp = await client.get(
        "/orders",
        headers={**TENANT_HEADER, "Authorization": f"Bearer {pre_mfa_token}"},
    )
    assert orders_resp.status_code == 403


async def test_ts_001_043_wrong_password_returns_generic_401(
    client: AsyncClient, viewer_user: AdminUserModel
) -> None:
    """TS-001-043: Wrong password returns 401 with generic message."""
    response = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": viewer_user.email, "password": "WrongPassword!"},
    )

    assert response.status_code == 401, response.text
    body = response.json()
    detail = body.get("detail", body)
    assert detail.get("message") == "Invalid email or password"
    assert "access_token" not in body


async def test_ts_001_044_nonexistent_email_returns_generic_401(
    client: AsyncClient,
) -> None:
    """TS-001-044: Non-existent email returns same generic 401 (anti-enumeration)."""
    response = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": "nobody@example.com", "password": "AnyPassword!"},
    )

    assert response.status_code == 401, response.text
    body = response.json()
    detail = body.get("detail", body)
    assert detail.get("message") == "Invalid email or password"


async def test_ts_001_045_pre_mfa_jwt_cannot_access_admin_endpoints(
    client: AsyncClient, owner_user: AdminUserModel
) -> None:
    """TS-001-045: Pre-MFA JWT returns 403 on GET /orders."""
    # Login as owner (mfa_required=True)
    login_resp = await client.post(
        "/auth/login",
        headers=TENANT_HEADER,
        json={"email": owner_user.email, "password": "ValidPass123!"},
    )
    assert login_resp.status_code == 200
    pre_mfa_token = login_resp.json()["access_token"]
    assert login_resp.json().get("mfa_required") is True

    # Pre-MFA token must be rejected
    orders_resp = await client.get(
        "/orders",
        headers={**TENANT_HEADER, "Authorization": f"Bearer {pre_mfa_token}"},
    )
    assert orders_resp.status_code == 403
    body = orders_resp.json()
    detail = body.get("detail", body)
    assert detail.get("code") == "MFA_REQUIRED"
