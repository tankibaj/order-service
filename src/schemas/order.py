"""Pydantic schemas for order endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from src.schemas.common import Address, PaymentMethodInput

# ─── Request schemas ────────────────────────────────────────────────────────


class OrderLineRequest(BaseModel):
    sku_id: uuid.UUID
    quantity: int = Field(ge=1)


class PlaceGuestOrderRequest(BaseModel):
    email: EmailStr
    shipping_address: Address
    shipping_method_id: uuid.UUID
    payment_method: PaymentMethodInput
    lines: list[OrderLineRequest] = Field(min_length=1)


# ─── Response schemas ────────────────────────────────────────────────────────


class OrderLineResponse(BaseModel):
    sku_id: uuid.UUID
    product_name: str
    variant_label: str | None = None
    quantity: int
    unit_price: int
    subtotal: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, line: object) -> "OrderLineResponse":
        from src.models.order import OrderLineModel

        assert isinstance(line, OrderLineModel)
        return cls(
            sku_id=line.sku_id,
            product_name=line.product_name,
            variant_label=line.variant_label,
            quantity=line.quantity,
            unit_price=line.unit_price_minor,
            subtotal=line.subtotal_minor,
        )


class OrderResponse(BaseModel):
    id: uuid.UUID
    reference: str
    status: str
    guest_email: str | None = None
    lines: list[OrderLineResponse]
    subtotal: int
    shipping_cost: int
    tax: int
    total: int
    shipping_address: Address
    notification_id: uuid.UUID | None = None
    notification_status: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, order: object) -> "OrderResponse":
        from src.models.order import OrderModel

        assert isinstance(order, OrderModel)
        return cls(
            id=order.id,
            reference=order.reference,
            status=order.status,
            guest_email=order.guest_email,
            lines=[OrderLineResponse.from_model(line) for line in order.lines],
            subtotal=order.subtotal_minor,
            shipping_cost=order.shipping_cost_minor,
            tax=order.tax_minor,
            total=order.total_minor,
            shipping_address=Address(**order.shipping_address),
            notification_id=order.notification_id,
            notification_status=order.notification_status,
            created_at=order.created_at,
        )


class OrderPageMeta(BaseModel):
    total: int
    page: int
    per_page: int


class OrderPage(BaseModel):
    data: list[OrderResponse]
    meta: OrderPageMeta
