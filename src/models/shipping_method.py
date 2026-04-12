import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ShippingMethodModel(Base):
    __tablename__ = "shipping_methods"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_shipping_methods_tenant_name"),
        CheckConstraint("cost_minor >= 0", name="ck_shipping_methods_cost_minor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cost_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_days_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_days_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(__import__("datetime").timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(__import__("datetime").timezone.utc),
    )
