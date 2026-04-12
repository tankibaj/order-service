import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class GuestSessionModel(Base):
    __tablename__ = "guest_sessions"
    __table_args__ = (
        Index("idx_guest_sessions_token", "token", unique=True),
        Index("idx_guest_sessions_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(__import__("datetime").timezone.utc),
    )
