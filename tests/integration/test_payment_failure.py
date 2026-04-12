"""
Integration tests for payment failure compensation in order placement saga.

Covers TS-001-030, TS-001-031.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import AsyncClient, Response

from src.clients.stripe_client import PaymentError, StripeClient
from src.services.guest_session_service import create_guest_session
from tests.conftest import TEST_TENANT_ID

EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _order_body(sku_id: str, shipping_method_id: str) -> dict:  # type: ignore[type-arg]
    return {
        "email": "grace@example.com",
        "shipping_address": {
            "line1": "123 Main St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country_code": "GB",
        },
        "shipping_method_id": shipping_method_id,
        "payment_method": {"type": "card", "token": "tok_fail_test"},
        "lines": [{"sku_id": sku_id, "quantity": 2}],
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
        name = "PaymentFailureStandard"
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


async def test_ts_001_030_payment_failure_triggers_stock_release(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-030: Payment failure triggers stock reservation release."""
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    sku_id = str(uuid.uuid4())
    reservation_id = str(uuid.uuid4())

    stripe_mock = AsyncMock(side_effect=PaymentError("Card declined"))
    release_call_count = 0
    deduct_called = False

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:

        def release_handler(request):  # type: ignore[no-untyped-def]
            nonlocal release_call_count
            release_call_count += 1
            return Response(204)

        def deduct_handler(request):  # type: ignore[no-untyped-def]
            nonlocal deduct_called
            deduct_called = True
            return Response(204)

        inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200,
                json={"reservation_id": reservation_id, "expires_at": EXPIRES_AT},
            )
        )
        inv_mock.post(f"/stock/reservations/{reservation_id}/release").mock(
            side_effect=release_handler
        )
        inv_mock.post("/stock/deduct").mock(side_effect=deduct_handler)

        with patch.object(StripeClient, "create_payment_intent", stripe_mock):
            response = await client.post(
                "/checkout/guest/orders",
                json=_order_body(sku_id, str(shipping_method.id)),
                headers={
                    "X-Guest-Session-Token": session.token,
                    "X-Tenant-ID": str(TEST_TENANT_ID),
                },
            )

    # Payment failed — response should indicate failure (not 201)
    assert response.status_code != 201, response.text
    assert response.status_code in (402, 400, 500), response.text

    # Release was called exactly once
    assert release_call_count == 1

    # Deduct was never called
    assert not deduct_called


async def test_ts_001_031_payment_failure_does_not_persist_order(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-031: Payment failure does not persist an order, no deduct called."""
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    sku_id = str(uuid.uuid4())
    reservation_id = str(uuid.uuid4())
    unique_email = f"paymentfail-{uuid.uuid4()}@example.com"

    stripe_mock = AsyncMock(side_effect=PaymentError("Insufficient funds"))
    deduct_called = False

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:

        def deduct_handler(request):  # type: ignore[no-untyped-def]
            nonlocal deduct_called
            deduct_called = True
            return Response(204)

        inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200,
                json={"reservation_id": reservation_id, "expires_at": EXPIRES_AT},
            )
        )
        inv_mock.post(f"/stock/reservations/{reservation_id}/release").mock(
            return_value=Response(204)
        )
        inv_mock.post("/stock/deduct").mock(side_effect=deduct_handler)

        with patch.object(StripeClient, "create_payment_intent", stripe_mock):
            body = {
                "email": unique_email,
                "shipping_address": {
                    "line1": "123 Main St",
                    "city": "London",
                    "postal_code": "SW1A 1AA",
                    "country_code": "GB",
                },
                "shipping_method_id": str(shipping_method.id),
                "payment_method": {"type": "card", "token": "tok_fail"},
                "lines": [{"sku_id": sku_id, "quantity": 1}],
            }
            response = await client.post(
                "/checkout/guest/orders",
                json=body,
                headers={
                    "X-Guest-Session-Token": session.token,
                    "X-Tenant-ID": str(TEST_TENANT_ID),
                },
            )

    assert response.status_code != 201, response.text

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

    # Deduct was never called
    assert not deduct_called
