"""Order and OrderLine data access layer."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.order import OrderLineModel, OrderModel


@dataclass
class CreateOrderLineData:
    sku_id: uuid.UUID
    product_name: str
    variant_label: str | None
    quantity: int
    unit_price_minor: int
    subtotal_minor: int


@dataclass
class CreateOrderData:
    tenant_id: uuid.UUID
    reference: str
    status: str
    guest_email: str | None
    customer_id: uuid.UUID | None
    shipping_address: dict[str, object]
    shipping_method_id: uuid.UUID
    shipping_cost_minor: int
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    payment_intent_id: str | None
    idempotency_key: str | None
    notification_id: uuid.UUID | None
    notification_status: str | None
    lines: list[CreateOrderLineData]


class OrderRepository:
    """CRUD operations for Order and OrderLine."""

    async def create(self, db: AsyncSession, data: CreateOrderData) -> OrderModel:
        """Persist an Order with its lines in a single commit."""
        now = datetime.now(UTC)
        order = OrderModel(
            tenant_id=data.tenant_id,
            reference=data.reference,
            status=data.status,
            guest_email=data.guest_email,
            customer_id=data.customer_id,
            shipping_address=data.shipping_address,
            shipping_method_id=data.shipping_method_id,
            shipping_cost_minor=data.shipping_cost_minor,
            subtotal_minor=data.subtotal_minor,
            tax_minor=data.tax_minor,
            total_minor=data.total_minor,
            payment_intent_id=data.payment_intent_id,
            idempotency_key=data.idempotency_key,
            notification_id=data.notification_id,
            notification_status=data.notification_status,
            created_at=now,
            updated_at=now,
        )
        db.add(order)
        await db.flush()  # get order.id before creating lines

        for line_data in data.lines:
            line = OrderLineModel(
                order_id=order.id,
                sku_id=line_data.sku_id,
                product_name=line_data.product_name,
                variant_label=line_data.variant_label,
                quantity=line_data.quantity,
                unit_price_minor=line_data.unit_price_minor,
                subtotal_minor=line_data.subtotal_minor,
            )
            db.add(line)

        await db.commit()
        await db.refresh(order)

        # Reload with lines eagerly
        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order.id)
            .options(selectinload(OrderModel.lines))
        )
        loaded = result.scalar_one()
        return loaded

    async def get_by_id(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> OrderModel | None:
        """Get an order by ID, scoped to the tenant, with lines eagerly loaded."""
        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.tenant_id == tenant_id)
            .options(selectinload(OrderModel.lines))
        )
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[OrderModel], int]:
        """List orders for a tenant with optional status filter and search.

        Returns (orders, total_count).
        """
        base_query = select(OrderModel).where(OrderModel.tenant_id == tenant_id)
        if status:
            base_query = base_query.where(OrderModel.status == status)
        if q:
            search_term = f"%{q}%"
            base_query = base_query.where(
                or_(
                    OrderModel.reference.ilike(search_term),
                    OrderModel.guest_email.ilike(search_term),
                )
            )

        count_query = select(func.count()).select_from(base_query.subquery())
        total = await db.scalar(count_query) or 0

        paged_query = (
            base_query.order_by(OrderModel.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .options(selectinload(OrderModel.lines))
        )
        result = await db.execute(paged_query)
        orders = list(result.scalars().all())
        return orders, total

    async def save(self, db: AsyncSession, order: OrderModel) -> OrderModel:
        """Persist changes to an existing order and reload with lines eager-loaded."""
        order.updated_at = datetime.now(UTC)
        db.add(order)
        await db.commit()
        # Reload with lines to avoid lazy-loading in async context
        result = await db.execute(
            select(OrderModel)
            .where(OrderModel.id == order.id)
            .options(selectinload(OrderModel.lines))
        )
        return result.scalar_one()

    async def reference_exists(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        reference: str,
    ) -> bool:
        """Check if a reference already exists for the tenant."""
        result = await db.execute(
            select(OrderModel.id).where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.reference == reference,
            )
        )
        return result.scalar_one_or_none() is not None
