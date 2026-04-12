import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.config import settings

ACCESS_TOKEN_TTL_SECONDS = 1800  # 30 minutes
REFRESH_TOKEN_TTL_SECONDS = 604800  # 7 days
ALGORITHM = "HS256"

MFA_REQUIRED_ROLES = {"merchant_owner", "merchant_admin"}


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    mfa_verified: bool,
) -> tuple[str, int]:
    """
    Create a JWT access token.

    Returns (token, expires_in_seconds).
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "mfa_verified": mfa_verified,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)).timestamp()),
        "type": "access",
    }
    return _encode(payload), ACCESS_TOKEN_TTL_SECONDS


def create_refresh_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    mfa_verified: bool,
) -> str:
    """Create a JWT refresh token."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "mfa_verified": mfa_verified,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)).timestamp()),
        "type": "refresh",
    }
    return _encode(payload)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises jwt.InvalidTokenError subclasses on failure.
    """
    decoded: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
    )
    return decoded
