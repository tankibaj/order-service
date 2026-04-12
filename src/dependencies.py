import uuid
from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

# Async engine — created once at module load
_engine = create_async_engine(settings.database_url, echo=False)
_async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with _async_session_factory() as session:
        yield session


async def get_tenant_id(x_tenant_id: str = Header(...)) -> uuid.UUID:
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_TENANT_ID",
                "message": "X-Tenant-ID must be a valid UUID",
            },
        ) from exc
