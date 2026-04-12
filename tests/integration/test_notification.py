"""
Integration tests for post-order notification dispatch.

Covers TS-001-034, TS-001-035, TS-001-036.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import AsyncClient, Response

from src.clients.stripe_client import PaymentIntent, StripeClient
from src.services.guest_session_service import create_guest_session
from tests.conftest import TEST_TENANT_ID

RESERVATION_ID = str(uuid.uuid4())
NOTIFICATION_ID = str(uuid.uuid4())
EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
NOTIFICATION_CREATED_AT = datetime.now(timezone.utc).isoformat()


def _notification_receipt(notification_id: str = NOTIFICATION_ID) -> dict:  # type: ignore[type-arg]
    return {
        "id": notification_id,
        "status": "queued",
        "channel": "email",
        "template_id": "order_confirmation",
        "created_at": NOTIFICATION_CREATED_AT,
        "delivered_at": None,
    }


@pytest.fixture(scope="module")
async def shipping_method(engine):  # type: ignore[no-untyped-def]
    """Seed a shipping method for notification tests (module-scoped)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.models.shipping_method import ShippingMethodModel

    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        name = "NotificationTestStandard"
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
    return AsyncMock(return_value=PaymentIntent(id="pi_test_notify", status="succeeded"))


def _order_body(
    shipping_method_id: str,
    lines: list[dict] | None = None,  # type: ignore[type-arg]
    email: str = "grace@example.com",
) -> dict:  # type: ignore[type-arg]
    return {
        "email": email,
        "shipping_address": {
            "line1": "123 Main St",
            "city": "London",
            "postal_code": "SW1A 1AA",
            "country_code": "GB",
        },
        "shipping_method_id": shipping_method_id,
        "payment_method": {"type": "card", "token": "tok_visa_test"},
        "lines": lines or [{"sku_id": str(uuid.uuid4()), "quantity": 1}],
    }


async def test_ts_001_034_notification_sent_after_successful_order(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
    mock_stripe_success: AsyncMock,
) -> None:
    """TS-001-034: Notification-service is called after successful order placement.

    The POST /notifications request must contain:
    - channel: "email"
    - template_id: "order_confirmation"
    - recipient.address: guest email
    Order is returned with status: confirmed regardless of notification outcome.
    """
    session = await create_guest_session(db_session, TEST_TENANT_ID)

    with respx.mock(base_url="http://inventory-service:8001") as inv_mock:
        inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200, json={"reservation_id": RESERVATION_ID, "expires_at": EXPIRES_AT}
            )
        )
        inv_mock.post("/stock/deduct").mock(return_value=Response(204))

        with respx.mock(base_url="http://notification-service:8002") as notif_mock:
            notif_route = notif_mock.post("/notifications").mock(
                return_value=Response(202, json=_notification_receipt())
            )

            with patch.object(StripeClient, "create_payment_intent", mock_stripe_success):
                response = await client.post(
                    "/checkout/guest/orders",
                    json=_order_body(
                        shipping_method_id=str(shipping_method.id),
                        email="grace@example.com",
                    ),
                    headers={
                        "X-Guest-Session-Token": session.token,
                        "X-Tenant-ID": str(TEST_TENANT_ID),
                    },
                )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "confirmed"

    # Notification called exactly once
    assert notif_route.call_count == 1, (
        f"Expected 1 notification call, got {notif_route.call_count}"
    )

    # Inspect the notification request payload
    notif_request_body = json.loads(notif_route.calls.last.request.content)
    assert notif_request_body["channel"] == "email"
    assert notif_request_body["template_id"] == "order_confirmation"
    assert notif_request_body["recipient"]["address"] == "grace@example.com"


async def test_ts_001_035_notification_not_sent_when_order_fails(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-035: Notification-service is NOT called when stock reservation fails.

    inventory-service returns 409; the saga aborts and no notification is sent.
    """
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    sku_id = str(uuid.uuid4())

    conflict_payload = {
        "code": "STOCK_CONFLICT",
        "message": "Insufficient stock",
        "conflicts": [{"sku_id": sku_id, "requested": 1, "available": 0}],
    }

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:
        inv_mock.post("/stock/reserve").mock(return_value=Response(409, json=conflict_payload))

        with respx.mock(
            base_url="http://notification-service:8002", assert_all_called=False
        ) as notif_mock:
            notif_route = notif_mock.post("/notifications").mock(
                return_value=Response(202, json=_notification_receipt())
            )

            response = await client.post(
                "/checkout/guest/orders",
                json=_order_body(
                    shipping_method_id=str(shipping_method.id),
                    lines=[{"sku_id": sku_id, "quantity": 1}],
                ),
                headers={
                    "X-Guest-Session-Token": session.token,
                    "X-Tenant-ID": str(TEST_TENANT_ID),
                },
            )

    assert response.status_code == 409, response.text
    assert notif_route.call_count == 0, (
        f"Expected 0 notification calls, got {notif_route.call_count}"
    )


async def test_ts_001_036_notification_payload_includes_order_details(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
    shipping_method,  # type: ignore[no-untyped-def]
    mock_stripe_success: AsyncMock,
) -> None:
    """TS-001-036: Notification payload includes order reference, line items, and total.

    Place an order with 2 lines; verify the notification payload contains:
    - order_reference matching the order response reference
    - 2 line entries with product_name, quantity, unit_price
    - total formatted as a currency string
    """
    session = await create_guest_session(db_session, TEST_TENANT_ID)
    sku_id_1 = str(uuid.uuid4())
    sku_id_2 = str(uuid.uuid4())

    notif_id = str(uuid.uuid4())

    with respx.mock(base_url="http://inventory-service:8001") as inv_mock:
        inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200,
                json={"reservation_id": str(uuid.uuid4()), "expires_at": EXPIRES_AT},
            )
        )
        inv_mock.post("/stock/deduct").mock(return_value=Response(204))

        with respx.mock(base_url="http://notification-service:8002") as notif_mock:
            notif_route = notif_mock.post("/notifications").mock(
                return_value=Response(202, json=_notification_receipt(notification_id=notif_id))
            )

            with patch.object(StripeClient, "create_payment_intent", mock_stripe_success):
                response = await client.post(
                    "/checkout/guest/orders",
                    json=_order_body(
                        shipping_method_id=str(shipping_method.id),
                        lines=[
                            {"sku_id": sku_id_1, "quantity": 2},
                            {"sku_id": sku_id_2, "quantity": 1},
                        ],
                    ),
                    headers={
                        "X-Guest-Session-Token": session.token,
                        "X-Tenant-ID": str(TEST_TENANT_ID),
                    },
                )

    assert response.status_code == 201, response.text
    order_body = response.json()
    order_reference = order_body["reference"]

    assert notif_route.call_count == 1

    notif_request_body = json.loads(notif_route.calls.last.request.content)
    notif_payload = notif_request_body["payload"]

    # order_reference matches the order response
    assert notif_payload["order_reference"] == order_reference, (
        f"order_reference mismatch: {notif_payload['order_reference']} != {order_reference}"
    )

    # Two line items with required fields
    assert len(notif_payload["lines"]) == 2, (
        f"Expected 2 notification lines, got {len(notif_payload['lines'])}"
    )
    for line in notif_payload["lines"]:
        assert "product_name" in line, f"Missing product_name in line: {line}"
        assert "quantity" in line, f"Missing quantity in line: {line}"
        assert "unit_price" in line, f"Missing unit_price in line: {line}"
        assert isinstance(line["product_name"], str)
        assert isinstance(line["quantity"], int)
        assert isinstance(line["unit_price"], str)

    # Total is a formatted currency string
    assert "total" in notif_payload
    total_str = notif_payload["total"]
    assert isinstance(total_str, str)
    assert total_str.startswith("$"), f"Expected total to start with '$', got: {total_str}"
