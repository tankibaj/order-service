"""
Integration tests for stock conflict handling in order placement.

Covers TS-001-027, TS-001-028.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import AsyncClient, Response

from src.clients.stripe_client import PaymentIntent, StripeClient
from src.services.guest_session_service import create_guest_session
from tests.conftest import TEST_TENANT_ID

EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _order_body(sku_id: str, quantity: int, shipping_method_id: str) -> dict:  # type: ignore[type-arg]
    return {
        "email": "grace@example.com",
        "shipping_address": {
            "line1": "123 Main St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country_code": "GB",
        },
        "shipping_method_id": shipping_method_id,
        "payment_method": {"type": "card", "token": "tok_visa_test"},
        "lines": [{"sku_id": sku_id, "quantity": quantity}],
    }


@pytest.fixture(scope="module")
async def shipping_method(engine):  # type: ignore[no-untyped-def]
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.models.shipping_method import ShippingMethodModel

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        name = "StockConflictStandard"
        result = await session.execute(
            select(ShippingMethodModel).where(
                ShippingMethodModel.tenant_id == TEST_TENANT_ID,
                ShippingMethodModel.name == name,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        method = ShippingMethodModel(
            tenant_id=TEST_TENANT_ID,
            name=name,
            cost_minor=599,
            is_active=True,
        )
        session.add(method)
        await session.commit()
        await session.refresh(method)
        return method


async def test_ts_001_027_insufficient_stock_returns_409(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-027: Insufficient stock returns 409 with conflict details."""
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    sku_id = str(uuid.uuid4())

    conflict_response = {
        "code": "STOCK_CONFLICT",
        "message": "Insufficient stock",
        "conflicts": [{"sku_id": sku_id, "requested": 5, "available": 2}],
    }

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:
        inv_mock.post("/stock/reserve").mock(return_value=Response(409, json=conflict_response))

        response = await client.post(
            "/checkout/guest/orders",
            json=_order_body(sku_id, 5, str(shipping_method.id)),
            headers={
                "X-Guest-Session-Token": session.token,
                "X-Tenant-ID": str(TEST_TENANT_ID),
            },
        )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "STOCK_CONFLICT"
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["sku_id"] == sku_id
    assert body["conflicts"][0]["requested"] == 5
    assert body["conflicts"][0]["available"] == 2


async def test_ts_001_028_stock_conflict_prevents_payment(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-028: Stock conflict prevents payment capture and no order is persisted."""
    unique_email = f"stockconflict-{uuid.uuid4()}@example.com"
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    sku_id = str(uuid.uuid4())

    conflict_response = {
        "code": "STOCK_CONFLICT",
        "message": "Insufficient stock",
        "conflicts": [{"sku_id": sku_id, "requested": 5, "available": 2}],
    }

    stripe_mock = AsyncMock(return_value=PaymentIntent(id="pi_test_123", status="succeeded"))
    deduct_called = False

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:

        def deduct_handler(request):  # type: ignore[no-untyped-def]
            nonlocal deduct_called
            deduct_called = True
            return Response(204)

        inv_mock.post("/stock/reserve").mock(return_value=Response(409, json=conflict_response))
        inv_mock.post("/stock/deduct").mock(side_effect=deduct_handler)

        body = _order_body(sku_id, 5, str(shipping_method.id))
        body["email"] = unique_email

        with patch.object(StripeClient, "create_payment_intent", stripe_mock):
            response = await client.post(
                "/checkout/guest/orders",
                json=body,
                headers={
                    "X-Guest-Session-Token": session.token,
                    "X-Tenant-ID": str(TEST_TENANT_ID),
                },
            )

    assert response.status_code == 409, response.text
    # Payment mock was never called
    assert stripe_mock.call_count == 0
    # Deduct was never called
    assert not deduct_called

    # No order persisted for this unique email
    from sqlalchemy import select

    from src.models.order import OrderModel

    result = await db_session.execute(
        select(OrderModel).where(
            OrderModel.guest_email == unique_email,
            OrderModel.tenant_id == TEST_TENANT_ID,
        )
    )
    orders = result.scalars().all()
    assert len(orders) == 0, f"Expected no orders, found {len(orders)}"
