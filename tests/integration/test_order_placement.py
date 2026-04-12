"""
Integration tests for order placement saga.

Covers TS-001-021, TS-001-022, TS-001-023, TS-001-059, TS-001-060, TS-001-061.
"""

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import AsyncClient, Response

from src.api.v1.checkout import get_inventory_client, get_notification_client, get_stripe_client
from src.clients.inventory_client import InventoryClient
from src.clients.notification_client import NotificationClient
from src.clients.stripe_client import PaymentIntent, StripeClient
from src.models.guest_session import GuestSessionModel
from src.services.guest_session_service import create_guest_session
from tests.conftest import TEST_TENANT_ID

VALID_SKU_ID = str(uuid.uuid4())
RESERVATION_ID = str(uuid.uuid4())
NOTIFICATION_ID = str(uuid.uuid4())
EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _order_body(sku_id: str = VALID_SKU_ID, shipping_method_id: str | None = None) -> dict:  # type: ignore[type-arg]
    return {
        "email": "grace@example.com",
        "shipping_address": {
            "line1": "123 Main St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country_code": "GB",
        },
        "shipping_method_id": shipping_method_id or str(uuid.uuid4()),
        "payment_method": {"type": "card", "token": "tok_visa_test"},
        "lines": [{"sku_id": sku_id, "quantity": 2}],
    }


@pytest.fixture
async def guest_session_token(db_session):  # type: ignore[no-untyped-def]
    """Create a valid guest session and return its token."""
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    return session.token


@pytest.fixture(scope="module")
async def shipping_method(engine):  # type: ignore[no-untyped-def]
    """Seed a shipping method for order placement tests (module-scoped to avoid duplicates)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.models.shipping_method import ShippingMethodModel

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        # Try to find an existing method by name to avoid duplicate inserts
        name = "OrderPlacementStandard"
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


@pytest.fixture
def mock_stripe_success() -> AsyncMock:
    """Mock StripeClient.create_payment_intent to return success."""
    mock = AsyncMock(return_value=PaymentIntent(id="pi_test_123", status="succeeded"))
    return mock


@pytest.fixture
def mock_stripe_failure() -> AsyncMock:
    """Mock StripeClient.create_payment_intent to raise PaymentError."""
    from src.clients.stripe_client import PaymentError

    mock = AsyncMock(side_effect=PaymentError("Card declined"))
    return mock


async def test_ts_001_021_successful_order_returns_201(
    client: AsyncClient,
    app,  # type: ignore[no-untyped-def]
    guest_session_token: str,
    shipping_method,  # type: ignore[no-untyped-def]
    mock_stripe_success: AsyncMock,
) -> None:
    """TS-001-021: Successful order placement returns 201 with confirmed order."""
    with respx.mock(base_url="http://inventory-service:8001") as inv_mock:
        inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200,
                json={"reservation_id": RESERVATION_ID, "expires_at": EXPIRES_AT},
            )
        )
        inv_mock.post("/stock/deduct").mock(return_value=Response(204))

        with respx.mock(base_url="http://notification-service:8002") as notif_mock:
            notif_mock.post("/notifications").mock(
                return_value=Response(202, json={"id": NOTIFICATION_ID})
            )

            with patch.object(StripeClient, "create_payment_intent", mock_stripe_success):
                response = await client.post(
                    "/checkout/guest/orders",
                    json=_order_body(shipping_method_id=str(shipping_method.id)),
                    headers={
                        "X-Guest-Session-Token": guest_session_token,
                        "X-Tenant-ID": str(TEST_TENANT_ID),
                    },
                )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert re.match(r"ORD-\d{8}-[0-9A-F]{4}", body["reference"]), body["reference"]
    assert len(body["lines"]) == 1
    assert body["lines"][0]["sku_id"] == VALID_SKU_ID
    assert body["lines"][0]["quantity"] == 2
    assert body["total"] > 0


async def test_ts_001_022_saga_executes_steps_in_order(
    client: AsyncClient,
    guest_session_token: str,
    shipping_method,  # type: ignore[no-untyped-def]
    mock_stripe_success: AsyncMock,
) -> None:
    """TS-001-022: Saga executes reserve → capture → deduct → notify in correct order."""
    call_order: list[str] = []
    reserve_call_count = 0
    deduct_call_count = 0
    notify_call_count = 0

    with respx.mock(base_url="http://inventory-service:8001") as inv_mock:

        def reserve_handler(request):  # type: ignore[no-untyped-def]
            nonlocal reserve_call_count
            call_order.append("reserve")
            reserve_call_count += 1
            return Response(200, json={"reservation_id": RESERVATION_ID, "expires_at": EXPIRES_AT})

        def deduct_handler(request):  # type: ignore[no-untyped-def]
            nonlocal deduct_call_count
            call_order.append("deduct")
            deduct_call_count += 1
            return Response(204)

        inv_mock.post("/stock/reserve").mock(side_effect=reserve_handler)
        inv_mock.post("/stock/deduct").mock(side_effect=deduct_handler)

        with respx.mock(base_url="http://notification-service:8002") as notif_mock:

            def notif_handler(request):  # type: ignore[no-untyped-def]
                nonlocal notify_call_count
                call_order.append("notify")
                notify_call_count += 1
                return Response(202, json={"id": NOTIFICATION_ID})

            notif_mock.post("/notifications").mock(side_effect=notif_handler)

            original_create = mock_stripe_success

            async def capture_wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
                call_order.append("capture")
                return await original_create(*args, **kwargs)

            with patch.object(StripeClient, "create_payment_intent", capture_wrapper):
                response = await client.post(
                    "/checkout/guest/orders",
                    json=_order_body(shipping_method_id=str(shipping_method.id)),
                    headers={
                        "X-Guest-Session-Token": guest_session_token,
                        "X-Tenant-ID": str(TEST_TENANT_ID),
                    },
                )

    assert response.status_code == 201, response.text
    assert call_order == ["reserve", "capture", "deduct", "notify"], call_order
    assert reserve_call_count == 1
    assert deduct_call_count == 1
    assert notify_call_count == 1


async def test_ts_001_023_order_references_are_unique(
    client: AsyncClient,
    guest_session_token: str,
    shipping_method,  # type: ignore[no-untyped-def]
    mock_stripe_success: AsyncMock,
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-023: Two placed orders have different references matching ORD-YYYYMMDD-XXXX."""
    references = []

    for _ in range(2):
        # Need a fresh guest session token per request
        session = await create_guest_session(db_session, TEST_TENANT_ID)

        with respx.mock(base_url="http://inventory-service:8001") as inv_mock:
            inv_mock.post("/stock/reserve").mock(
                return_value=Response(
                    200,
                    json={"reservation_id": str(uuid.uuid4()), "expires_at": EXPIRES_AT},
                )
            )
            inv_mock.post("/stock/deduct").mock(return_value=Response(204))

            with respx.mock(base_url="http://notification-service:8002") as notif_mock:
                notif_mock.post("/notifications").mock(
                    return_value=Response(202, json={"id": str(uuid.uuid4())})
                )

                with patch.object(StripeClient, "create_payment_intent", mock_stripe_success):
                    response = await client.post(
                        "/checkout/guest/orders",
                        json=_order_body(shipping_method_id=str(shipping_method.id)),
                        headers={
                            "X-Guest-Session-Token": session.token,
                            "X-Tenant-ID": str(TEST_TENANT_ID),
                        },
                    )

        assert response.status_code == 201, response.text
        ref = response.json()["reference"]
        assert re.match(r"ORD-\d{8}-[0-9A-F]{4}", ref), ref
        references.append(ref)

    assert references[0] != references[1], f"References should be unique: {references}"
