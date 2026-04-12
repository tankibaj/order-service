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

    async def get_by_id(
        self,
        db: AsyncSession,
        shipping_method_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> ShippingMethodModel | None:
        result = await db.execute(
            select(ShippingMethodModel).where(
                ShippingMethodModel.id == shipping_method_id,
                ShippingMethodModel.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()
