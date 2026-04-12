"""Shared test fixtures for order-service tests."""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.dependencies import get_db
from src.main import create_app
from src.models.base import Base
from src.models.guest_session import GuestSessionModel
from src.models.shipping_method import ShippingMethodModel

# Test database URL — use a dedicated test DB to avoid polluting the app DB
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5433/app"),
)

# Well-known test tenant
TEST_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Session-scoped async engine with clean schema."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped DB session. Commits are real; tests must clean up their data."""
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest.fixture
async def app(engine: AsyncEngine) -> AsyncGenerator[object, None]:
    """FastAPI app with get_db overridden to use the test engine."""
    _app = create_app()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    _app.dependency_overrides[get_db] = override_get_db
    yield _app
    _app.dependency_overrides.clear()


@pytest.fixture
async def client(app: object) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client targeting the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    ) as ac:
        yield ac


# ── Data helpers ──────────────────────────────────────────────────────────────


async def create_shipping_methods(db: AsyncSession) -> list[ShippingMethodModel]:
    """Seed two shipping methods for TEST_TENANT_ID."""
    standard = ShippingMethodModel(
        tenant_id=TEST_TENANT_ID,
        name="Standard Shipping",
        description="Delivery in 3-5 business days",
        cost_minor=599,
        estimated_days_min=3,
        estimated_days_max=5,
        is_active=True,
    )
    express = ShippingMethodModel(
        tenant_id=TEST_TENANT_ID,
        name="Express Shipping",
        description="Delivery in 1-2 business days",
        cost_minor=1499,
        estimated_days_min=1,
        estimated_days_max=2,
        is_active=True,
    )
    db.add_all([standard, express])
    await db.commit()
    await db.refresh(standard)
    await db.refresh(express)
    return [standard, express]


async def create_expired_guest_session(db: AsyncSession, tenant_id: uuid.UUID) -> GuestSessionModel:
    """Create a guest session that has already expired."""
    import secrets

    session = GuestSessionModel(
        tenant_id=tenant_id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
