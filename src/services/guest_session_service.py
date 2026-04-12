import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.guest_session import GuestSessionModel
from src.repositories.guest_session_repo import GuestSessionRepository

SESSION_TTL_HOURS = 24
_repo = GuestSessionRepository()


async def create_guest_session(db: AsyncSession, tenant_id: uuid.UUID) -> GuestSessionModel:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=SESSION_TTL_HOURS)
    return await _repo.create(db, tenant_id, token, expires_at)


async def validate_guest_session(db: AsyncSession, token: str) -> GuestSessionModel:
    session = await _repo.get_by_token(db, token)
    if not session:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SESSION", "message": "Invalid session token"},
        )
    # Handle both naive and aware datetimes from the DB
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=401,
            detail={"code": "SESSION_EXPIRED", "message": "Guest session has expired"},
        )
    return session
