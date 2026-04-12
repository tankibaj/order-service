import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.admin_user import AdminUserModel


class AdminUserRepository:
    async def get_by_email_and_tenant(
        self,
        db: AsyncSession,
        email: str,
        tenant_id: uuid.UUID,
    ) -> AdminUserModel | None:
        result = await db.execute(
            select(AdminUserModel).where(
                AdminUserModel.email == email,
                AdminUserModel.tenant_id == tenant_id,
                AdminUserModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, user_id: uuid.UUID) -> AdminUserModel | None:
        result = await db.execute(
            select(AdminUserModel).where(
                AdminUserModel.id == user_id,
                AdminUserModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
