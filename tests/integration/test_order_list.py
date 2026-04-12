"""
Integration tests for GET /orders (admin order list).

Covers TS-001-046, TS-001-047, TS-001-048, TS-001-049, TS-001-050, TS-001-054.
"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.models.order import OrderLineModel, OrderModel
from src.services.jwt_service import create_access_token
from tests.conftest import TEST_TENANT_ID

# A second test tenant
TENANT_B_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

# Admin user IDs (don't need to exist in DB — JWT-only auth)
ADMIN_USER_ID = uuid.UUID("00000000-1111-0000-0000-000000000001")
TENANT_B_USER_ID = uuid.UUID("00000000-1111-0000-0000-000000000002")


def _make_admin_token(tenant_id: uuid.UUID = TEST_TENANT_ID, role: str = "viewer") -> str:
    """Generate a valid viewer JWT for tests (viewer doesn't require MFA)."""
    token, _ = create_access_token(
        user_id=ADMIN_USER_ID,
        tenant_id=tenant_id,
        role=role,
        mfa_verified=True,
    )
    return token


def _auth_headers(tenant_id: uuid.UUID = TEST_TENANT_ID) -> dict:  # type: ignore[type-arg]
    return {
        "Authorization": f"Bearer {_make_admin_token(tenant_id)}",
        "X-Tenant-ID": str(tenant_id),
    }


async def _seed_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reference: str,
    status: str = "confirmed",
    guest_email: str = "test@example.com",
    num_lines: int = 1,
) -> OrderModel:
    """Helper: insert an order with N lines."""
    now = datetime.now(timezone.utc)
    order = OrderModel(
        tenant_id=tenant_id,
        reference=reference,
        status=status,
        guest_email=guest_email,
        shipping_address={
            "line1": "1 Test St",
            "city": "London",
            "postal_code": "SW1",
            "country_code": "GB",
        },
        shipping_method_id=uuid.uuid4(),
        shipping_cost_minor=599,
        subtotal_minor=1000,
        tax_minor=0,
        total_minor=1599,
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
            quantity=1,
            unit_price_minor=1000,
            subtotal_minor=1000,
        )
        session.add(line)

    await session.commit()
    await session.refresh(order)
    return order


@pytest.fixture(scope="module")
async def seeded_orders(engine):  # type: ignore[no-untyped-def]
    """Seed orders for both tenants for WP-007 tests."""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        # Clear any prior orders for these tenants to get a clean count
        existing_a = await session.execute(
            select(OrderModel).where(OrderModel.tenant_id == TEST_TENANT_ID)
        )
        existing_b = await session.execute(
            select(OrderModel).where(OrderModel.tenant_id == TENANT_B_ID)
        )
        for o in existing_a.scalars().all():
            await session.delete(o)
        for o in existing_b.scalars().all():
            await session.delete(o)
        await session.commit()

        # Tenant A: 25 orders — 6 confirmed, 4 pending, rest confirmed
        for i in range(25):
            status = "pending" if i < 4 else "confirmed"
            email = "grace@example.com" if i < 2 else f"user{i}@example.com"
            ref = f"ORD-20260412-{i:04d}"
            await _seed_order(session, TEST_TENANT_ID, ref, status=status, guest_email=email)

        # Tenant B: 3 orders
        for i in range(3):
            await _seed_order(session, TENANT_B_ID, f"ORD-20260412-B{i:03d}")

    return {"tenant_a_count": 25, "tenant_b_count": 3}


async def test_ts_001_046_paginated_list_returns_20_orders(
    client: AsyncClient,
    seeded_orders: dict,  # type: ignore[type-arg]
) -> None:
    """TS-001-046: Paginated order list returns orders with metadata."""
    response = await client.get(
        "/orders?page=1&per_page=20",
        headers=_auth_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert len(body["data"]) == 20
    assert body["meta"]["total"] == 25
    assert body["meta"]["page"] == 1
    assert body["meta"]["per_page"] == 20
    # Verify each order has required fields
    for order in body["data"]:
        assert "id" in order
        assert "reference" in order
        assert "status" in order
        assert "total" in order
        assert "created_at" in order


async def test_ts_001_047_orders_scoped_to_tenant(
    client: AsyncClient,
    seeded_orders: dict,  # type: ignore[type-arg]
) -> None:
    """TS-001-047: Orders are scoped to the authenticated tenant."""
    # Tenant A sees only 25 orders
    response_a = await client.get("/orders?per_page=100", headers=_auth_headers(TEST_TENANT_ID))
    assert response_a.status_code == 200
    body_a = response_a.json()
    assert body_a["meta"]["total"] == 25

    # Tenant B sees only 3 orders
    response_b = await client.get("/orders?per_page=100", headers=_auth_headers(TENANT_B_ID))
    assert response_b.status_code == 200
    body_b = response_b.json()
    assert body_b["meta"]["total"] == 3

    # No Tenant B orders appear in Tenant A results
    tenant_a_order_ids = {o["id"] for o in body_a["data"]}
    tenant_b_order_ids = {o["id"] for o in body_b["data"]}
    assert tenant_a_order_ids.isdisjoint(tenant_b_order_ids)


async def test_ts_001_048_search_by_reference(
    client: AsyncClient,
    seeded_orders: dict,  # type: ignore[type-arg]
) -> None:
    """TS-001-048: Search by order reference returns matching orders."""
    # ORD-20260412-0005 is a confirmed order
    response = await client.get("/orders?q=0005", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] >= 1
    assert any("0005" in o["reference"] for o in body["data"])


async def test_ts_001_049_search_by_guest_email(
    client: AsyncClient,
    seeded_orders: dict,  # type: ignore[type-arg]
) -> None:
    """TS-001-049: Search by guest email returns matching orders."""
    response = await client.get("/orders?q=grace@example.com", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    # 2 orders have grace@example.com
    assert body["meta"]["total"] == 2
    for order in body["data"]:
        assert order["guest_email"] == "grace@example.com"


async def test_ts_001_050_status_filter(
    client: AsyncClient,
    seeded_orders: dict,  # type: ignore[type-arg]
) -> None:
    """TS-001-050: Status filter returns only matching orders."""
    response = await client.get("/orders?status=confirmed", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    # 25 - 4 pending = 21 confirmed
    assert body["meta"]["total"] == 21
    for order in body["data"]:
        assert order["status"] == "confirmed"

    # Pending filter
    response_pending = await client.get("/orders?status=pending", headers=_auth_headers())
    body_pending = response_pending.json()
    assert body_pending["meta"]["total"] == 4
    for order in body_pending["data"]:
        assert order["status"] == "pending"


async def test_ts_001_054_empty_order_list(
    client: AsyncClient,
) -> None:
    """TS-001-054: Empty order list returns 200 with data=[] and meta.total=0."""
    # Use a tenant with no orders
    empty_tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    response = await client.get(
        "/orders",
        headers={
            "Authorization": f"Bearer {_make_admin_token(empty_tenant_id)}",
            "X-Tenant-ID": str(empty_tenant_id),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0
