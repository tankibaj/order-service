import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.shipping_method import ShippingMethodModel


class ShippingMethodRepository:
    async def list_active(
        self, db: AsyncSession, tenant_id: uuid.UUID
    ) -> list[ShippingMethodModel]:
        result = await db.execute(
            select(ShippingMethodModel).where(
                ShippingMethodModel.tenant_id == tenant_id,
                ShippingMethodModel.is_active.is_(True),
            )
        )
        return list(result.scalars().all())
