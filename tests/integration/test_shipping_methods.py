"""
Integration tests for shipping methods endpoint.

TS scenarios covered:
  TS-001-018 — GET /checkout/shipping-methods returns shipping options
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TEST_TENANT_ID, create_shipping_methods

TENANT_HEADER = {"X-Tenant-ID": str(TEST_TENANT_ID)}


async def test_ts_001_018_shipping_methods_returned(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """TS-001-018: GET /checkout/shipping-methods returns at least 2 methods with correct schema."""
    # Seed shipping methods
    await create_shipping_methods(db_session)

    response = await client.get(
        "/checkout/shipping-methods",
        headers=TENANT_HEADER,
    )

    assert response.status_code == 200
    methods = response.json()

    # At least 2 shipping methods
    assert len(methods) >= 2, f"Expected >= 2 shipping methods, got {len(methods)}"

    # Validate schema for each method
    for method in methods:
        assert "id" in method, "ShippingMethod missing 'id'"
        assert "name" in method, "ShippingMethod missing 'name'"
        assert "cost_minor" in method, "ShippingMethod missing 'cost_minor'"

        # Required fields must have valid types
        import uuid

        uuid.UUID(method["id"])  # Must be a valid UUID
        assert isinstance(method["name"], str)
        assert isinstance(method["cost_minor"], int)

        # Optional fields — check presence (can be None)
        assert "description" in method
        assert "estimated_days_min" in method
        assert "estimated_days_max" in method

    # Verify our seeded methods are present
    names = [m["name"] for m in methods]
    assert "Standard Shipping" in names
    assert "Express Shipping" in names

    # Verify costs
    standard = next(m for m in methods if m["name"] == "Standard Shipping")
    assert standard["cost_minor"] == 599
    assert standard["estimated_days_min"] == 3
    assert standard["estimated_days_max"] == 5

    express = next(m for m in methods if m["name"] == "Express Shipping")
    assert express["cost_minor"] == 1499
    assert express["estimated_days_min"] == 1
    assert express["estimated_days_max"] == 2
