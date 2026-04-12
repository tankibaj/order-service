"""
Integration tests for guest session endpoints.

TS scenarios covered:
  TS-001-016 — POST /checkout/guest/sessions creates a guest session
  TS-001-017 — Guest session token is usable in subsequent requests
  TS-001-032 — Expired session token returns 401
  TS-001-033 — Invalid session token returns 401
"""

import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_TENANT_ID, create_expired_guest_session

TENANT_HEADER = {"X-Tenant-ID": str(TEST_TENANT_ID)}


async def test_ts_001_016_create_guest_session(client: AsyncClient) -> None:
    """TS-001-016: POST /checkout/guest/sessions returns 201 with GuestSession schema."""
    response = await client.post(
        "/checkout/guest/sessions",
        headers=TENANT_HEADER,
        json={},
    )

    assert response.status_code == 201
    body = response.json()

    # Schema: id (UUID), token (non-empty), expires_at (ISO 8601)
    assert "id" in body
    assert "token" in body
    assert "expires_at" in body

    # id must be a valid UUID
    parsed_id = uuid.UUID(body["id"])
    assert parsed_id is not None

    # token must be non-empty
    assert len(body["token"]) > 0

    # expires_at must be in the future (at least 23 hours from now)
    expires_at = datetime.fromisoformat(body["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    hours_from_now = (expires_at - now).total_seconds() / 3600
    assert hours_from_now >= 23, (
        f"expires_at is only {hours_from_now:.1f}h from now, expected >= 23h"
    )


async def test_ts_001_017_valid_session_token_accepted(client: AsyncClient) -> None:
    """TS-001-017: Valid session token is NOT rejected with 401."""
    # Step 1: Create a guest session
    create_resp = await client.post(
        "/checkout/guest/sessions",
        headers=TENANT_HEADER,
        json={},
    )
    assert create_resp.status_code == 201
    token = create_resp.json()["token"]

    # Step 2: Use the token on POST /checkout/guest/orders
    # Expected: NOT 401. The stub returns 422 for valid sessions.
    order_resp = await client.post(
        "/checkout/guest/orders",
        headers={**TENANT_HEADER, "X-Guest-Session-Token": token},
        json={},
    )
    assert order_resp.status_code != 401, (
        f"Valid session token was rejected with 401. Got: {order_resp.status_code}"
    )
    # The stub returns 422
    assert order_resp.status_code == 422


async def test_ts_001_032_expired_session_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TS-001-032: POST /checkout/guest/orders with expired token returns 401."""
    expired_session = await create_expired_guest_session(db_session, TEST_TENANT_ID)

    response = await client.post(
        "/checkout/guest/orders",
        headers={
            **TENANT_HEADER,
            "X-Guest-Session-Token": expired_session.token,
        },
        json={},
    )

    assert response.status_code == 401
    body = response.json()
    # FastAPI wraps our detail in a "detail" key for HTTPException
    detail = body.get("detail", body)
    assert detail.get("code") in ("SESSION_EXPIRED", "INVALID_SESSION")


async def test_ts_001_033_invalid_session_returns_401(client: AsyncClient) -> None:
    """TS-001-033: POST /checkout/guest/orders with garbage token returns 401."""
    response = await client.post(
        "/checkout/guest/orders",
        headers={
            **TENANT_HEADER,
            "X-Guest-Session-Token": "invalid-garbage-token",
        },
        json={},
    )

    assert response.status_code == 401
    body = response.json()
    detail = body.get("detail", body)
    assert detail.get("code") == "INVALID_SESSION"
