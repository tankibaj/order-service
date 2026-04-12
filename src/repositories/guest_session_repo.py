import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.guest_session import GuestSessionModel


class GuestSessionRepository:
    async def create(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        token: str,
        expires_at: datetime,
    ) -> GuestSessionModel:
        session = GuestSessionModel(
            tenant_id=tenant_id,
            token=token,
            expires_at=expires_at,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def get_by_token(self, db: AsyncSession, token: str) -> GuestSessionModel | None:
        result = await db.execute(select(GuestSessionModel).where(GuestSessionModel.token == token))
        return result.scalar_one_or_none()
