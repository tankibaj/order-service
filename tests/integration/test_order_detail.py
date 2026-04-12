"""
Integration tests for GET /orders/{orderId} (admin order detail).

Covers TS-001-051, TS-001-052, TS-001-053, TS-001-055.
"""

import uuid
from datetime import datetime, timezone

import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.order import OrderLineModel, OrderModel
from src.services.jwt_service import create_access_token
from tests.conftest import TEST_TENANT_ID

ADMIN_USER_ID = uuid.UUID("00000000-2222-0000-0000-000000000001")
NOTIFICATION_SERVICE_URL = "http://notification-service:8002"


def _auth_headers(tenant_id: uuid.UUID = TEST_TENANT_ID) -> dict:  # type: ignore[type-arg]
    token, _ = create_access_token(
        user_id=ADMIN_USER_ID,
        tenant_id=tenant_id,
        role="viewer",
        mfa_verified=True,
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-ID": str(tenant_id),
    }


async def _create_order(
    session: AsyncSession,
    tenant_id: uuid.UUID = TEST_TENANT_ID,
    status: str = "confirmed",
    notification_id: uuid.UUID | None = None,
    notification_status: str | None = None,
    num_lines: int = 2,
) -> OrderModel:
    """Helper: create an order with given properties."""
    now = datetime.now(timezone.utc)
    order = OrderModel(
        tenant_id=tenant_id,
        reference=f"ORD-20260412-DET{uuid.uuid4().hex[:4].upper()}",
        status=status,
        guest_email="grace@example.com",
        shipping_address={
            "line1": "123 Main St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country_code": "GB",
        },
        shipping_method_id=uuid.uuid4(),
        shipping_cost_minor=599,
        subtotal_minor=2000,
        tax_minor=0,
        total_minor=2599,
        notification_id=notification_id,
        notification_status=notification_status,
        created_at=now,
        updated_at=now,
    )
    session.add(order)
    await session.flush()

    for i in range(num_lines):
        line = OrderLineModel(
            order_id=order.id,
            sku_id=uuid.uuid4(),
            product_name=f"Product {i + 1}",
            variant_label="Standard",
            quantity=1,
            unit_price_minor=1000,
            subtotal_minor=1000,
        )
        session.add(line)

    await session.commit()
    await session.refresh(order)
    return order


@pytest.fixture(scope="module")
async def engine_session(engine):  # type: ignore[no-untyped-def]
    """Return a module-scoped session factory."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return factory


async def test_ts_001_051_order_detail_returns_full_order(
    client: AsyncClient,
    engine,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-051: Order detail returns full order with all fields."""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        order = await _create_order(session, num_lines=2)

    with respx.mock(base_url=NOTIFICATION_SERVICE_URL, assert_all_called=False):
        response = await client.get(
            f"/orders/{order.id}",
            headers=_auth_headers(),
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(order.id)
    assert body["reference"] == order.reference
    assert body["status"] == "confirmed"
    assert "created_at" in body
    assert len(body["lines"]) == 2
    for line in body["lines"]:
        assert "product_name" in line
        assert "variant_label" in line
        assert "quantity" in line
        assert "unit_price" in line
        assert "subtotal" in line
    assert body["shipping_address"]["line1"] == "123 Main St"
    assert body["shipping_address"]["city"] == "London"
    assert body["shipping_address"]["postal_code"] == "SW1A 1AA"
    assert body["shipping_address"]["country_code"] == "GB"
    assert body["total"] > 0


async def test_ts_001_052_failed_notification_shows_on_detail(
    client: AsyncClient,
    engine,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-052: Failed notification status is shown on order detail."""
    notification_id = uuid.uuid4()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        order = await _create_order(
            session,
            notification_id=notification_id,
            notification_status="failed",
        )

    # notification status is terminal — no sync call needed
    with respx.mock(base_url=NOTIFICATION_SERVICE_URL, assert_all_called=False):
        response = await client.get(f"/orders/{order.id}", headers=_auth_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notification_status"] == "failed"


async def test_ts_001_053_sent_notification_shows_on_detail(
    client: AsyncClient,
    engine,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-053: Sent notification shows on order detail."""
    notification_id = uuid.uuid4()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        order = await _create_order(
            session,
            notification_id=notification_id,
            notification_status="sent",
        )

    # notification status is terminal — no sync call
    with respx.mock(base_url=NOTIFICATION_SERVICE_URL, assert_all_called=False):
        response = await client.get(f"/orders/{order.id}", headers=_auth_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notification_status"] == "sent"


async def test_ts_001_055_nonexistent_order_returns_404(
    client: AsyncClient,
) -> None:
    """TS-001-055: Non-existent order returns 404."""
    non_existent_id = uuid.uuid4()

    with respx.mock(base_url=NOTIFICATION_SERVICE_URL, assert_all_called=False):
        response = await client.get(
            f"/orders/{non_existent_id}",
            headers=_auth_headers(),
        )

    assert response.status_code == 404, response.text
    body = response.json()
    assert "detail" in body or "message" in body or "code" in body


async def test_notification_sync_fetches_queued_status(
    client: AsyncClient,
    engine,  # type: ignore[no-untyped-def]
) -> None:
    """Verify lazy sync updates a 'queued' notification to 'delivered' from mock service."""
    notification_id = uuid.uuid4()
    now_iso = datetime.now(timezone.utc).isoformat()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        order = await _create_order(
            session,
            notification_id=notification_id,
            notification_status="queued",
        )

    with respx.mock(base_url=NOTIFICATION_SERVICE_URL) as notif_mock:
        notif_mock.get(f"/notifications/{notification_id}").mock(
            return_value=Response(
                200,
                json={
                    "id": str(notification_id),
                    "status": "delivered",
                    "channel": "email",
                    "template_id": "order_confirmation",
                    "created_at": now_iso,
                    "delivered_at": now_iso,
                },
            )
        )
        response = await client.get(f"/orders/{order.id}", headers=_auth_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["notification_status"] == "delivered"


async def test_notification_sync_graceful_on_service_failure(
    client: AsyncClient,
    engine,  # type: ignore[no-untyped-def]
) -> None:
    """Verify order detail returns stale status when notification-service is unreachable."""
    notification_id = uuid.uuid4()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        order = await _create_order(
            session,
            notification_id=notification_id,
            notification_status="queued",
        )

    with respx.mock(base_url=NOTIFICATION_SERVICE_URL) as notif_mock:
        notif_mock.get(f"/notifications/{notification_id}").mock(
            return_value=Response(503, json={"error": "service unavailable"})
        )
        response = await client.get(f"/orders/{order.id}", headers=_auth_headers())

    # Should still return 200 with stale notification status
    assert response.status_code == 200, response.text
    body = response.json()
    # Status remains as stale (queued) — not 500
    assert body["notification_status"] == "queued"
