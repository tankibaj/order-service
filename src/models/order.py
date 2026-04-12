import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class OrderModel(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference", name="uq_orders_tenant_reference"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_orders_tenant_idempotency_key"),
        CheckConstraint(
            "customer_id IS NOT NULL OR guest_email IS NOT NULL",
            name="ck_orders_customer_or_guest",
        ),
        Index("idx_orders_tenant_status", "tenant_id", "status"),
        Index(
            "idx_orders_guest_email",
            "guest_email",
            postgresql_where="guest_email IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reference: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    shipping_address: Mapped[dict] = mapped_column(JSONB, nullable=False)  # type: ignore[type-arg]
    shipping_method_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    shipping_cost_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    notification_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notification_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    payment_intent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    lines: Mapped[list["OrderLineModel"]] = relationship(
        "OrderLineModel", back_populates="order", cascade="all, delete-orphan"
    )


class OrderLineModel(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_order_lines_quantity"),
        CheckConstraint("unit_price_minor >= 0", name="ck_order_lines_unit_price"),
        Index("idx_order_lines_order_id", "order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    variant_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["OrderModel"] = relationship("OrderModel", back_populates="lines")
