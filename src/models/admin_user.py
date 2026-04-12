import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

VALID_ROLES = ("merchant_owner", "merchant_admin", "merchant_viewer", "merchant_support")


class AdminUserModel(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_admin_users_tenant_email"),
        CheckConstraint(
            "role IN ('merchant_owner', 'merchant_admin', 'merchant_viewer', 'merchant_support')",
            name="ck_admin_users_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
