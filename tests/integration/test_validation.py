"""
Integration tests for checkout request validation.

Covers TS-001-025, TS-001-026.
"""

import uuid
from datetime import datetime, timedelta, timezone

import respx
from httpx import AsyncClient, Response

from src.services.guest_session_service import create_guest_session
from tests.conftest import TEST_TENANT_ID

EXPIRES_AT = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
VALID_SKU_ID = str(uuid.uuid4())


def _full_order_body(
    sku_id: str = VALID_SKU_ID,
    shipping_method_id: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Build a valid order request body."""
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
        "lines": [{"sku_id": sku_id, "quantity": 1}],
    }


async def test_ts_001_025_missing_postal_code_returns_422(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-025: Missing postal_code returns 422 with field-level error.

    No stock reservation must be attempted.
    """
    session = await create_guest_session(db_session, TEST_TENANT_ID)

    body = {
        "email": "grace@example.com",
        "shipping_address": {
            "line1": "123 Main St",
            "city": "London",
            # postal_code intentionally omitted
            "country_code": "GB",
        },
        "shipping_method_id": str(uuid.uuid4()),
        "payment_method": {"type": "card", "token": "tok_visa_test"},
        "lines": [{"sku_id": str(uuid.uuid4()), "quantity": 1}],
    }

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:
        reserve_route = inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200,
                json={"reservation_id": str(uuid.uuid4()), "expires_at": EXPIRES_AT},
            )
        )

        response = await client.post(
            "/checkout/guest/orders",
            json=body,
            headers={
                "X-Guest-Session-Token": session.token,
                "X-Tenant-ID": str(TEST_TENANT_ID),
            },
        )

    assert response.status_code == 422, response.text
    resp_body = response.json()

    assert resp_body.get("code") == "VALIDATION_ERROR"
    assert "details" in resp_body
    details = resp_body["details"]
    assert isinstance(details, list)
    assert len(details) >= 1

    # At least one entry must reference postal_code
    fields = [d["field"] for d in details]
    assert any("postal_code" in f for f in fields), (
        f"Expected a 'postal_code' field error in details, got: {fields}"
    )

    # No stock reservation attempted
    assert reserve_route.call_count == 0, (
        f"Expected 0 inventory calls, got {reserve_route.call_count}"
    )


async def test_ts_001_026_multiple_missing_fields_return_multiple_errors(
    client: AsyncClient,
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    """TS-001-026: Multiple missing fields returns 422 with all field errors.

    Body is missing email, shipping_address.line1, and shipping_address.postal_code.
    No stock reservation must be attempted.
    """
    session = await create_guest_session(db_session, TEST_TENANT_ID)

    body: dict[str, object] = {
        # email intentionally omitted
        "shipping_address": {
            # line1 intentionally omitted
            "city": "London",
            # postal_code intentionally omitted
            "country_code": "GB",
        },
        "shipping_method_id": str(uuid.uuid4()),
        "payment_method": {"type": "card", "token": "tok_visa_test"},
        "lines": [{"sku_id": str(uuid.uuid4()), "quantity": 1}],
    }

    with respx.mock(base_url="http://inventory-service:8001", assert_all_called=False) as inv_mock:
        reserve_route = inv_mock.post("/stock/reserve").mock(
            return_value=Response(
                200,
                json={"reservation_id": str(uuid.uuid4()), "expires_at": EXPIRES_AT},
            )
        )

        response = await client.post(
            "/checkout/guest/orders",
            json=body,
            headers={
                "X-Guest-Session-Token": session.token,
                "X-Tenant-ID": str(TEST_TENANT_ID),
            },
        )

    assert response.status_code == 422, response.text
    resp_body = response.json()

    assert resp_body.get("code") == "VALIDATION_ERROR"
    details = resp_body.get("details", [])
    assert len(details) >= 3, (
        f"Expected at least 3 validation errors, got {len(details)}: {details}"
    )

    fields_joined = " ".join(d["field"] for d in details)
    assert "email" in fields_joined, f"Expected 'email' in field errors: {details}"
    assert "line1" in fields_joined, f"Expected 'line1' in field errors: {details}"
    assert "postal_code" in fields_joined, f"Expected 'postal_code' in field errors: {details}"

    # No stock reservation attempted
    assert reserve_route.call_count == 0, (
        f"Expected 0 inventory calls, got {reserve_route.call_count}"
    )
