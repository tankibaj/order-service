import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.admin_user_repo import AdminUserRepository
from src.services.jwt_service import (
    MFA_REQUIRED_ROLES,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.services.password_service import dummy_verify, verify_password
from src.services.totp_service import verify_totp

_repo = AdminUserRepository()

_INVALID_CREDENTIALS_ERROR = HTTPException(
    status_code=401,
    detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password"},
)


@dataclass
class LoginResult:
    access_token: str
    refresh_token: str
    expires_in: int
    mfa_required: bool


@dataclass
class AdminContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    mfa_verified: bool


async def login(
    db: AsyncSession,
    email: str,
    password: str,
    tenant_id: uuid.UUID,
) -> LoginResult:
    """
    Authenticate an admin user.

    For viewer/support roles: returns a fully authenticated JWT.
    For owner/admin roles: returns a pre-MFA JWT.
    """
    user = await _repo.get_by_email_and_tenant(db, email, tenant_id)

    if user is None:
        dummy_verify()  # Constant-time: anti-enumeration
        raise _INVALID_CREDENTIALS_ERROR

    if not verify_password(password, user.password_hash):
        raise _INVALID_CREDENTIALS_ERROR

    mfa_required = user.role in MFA_REQUIRED_ROLES
    mfa_verified = not mfa_required  # viewer/support start verified

    access_token, expires_in = create_access_token(user.id, user.tenant_id, user.role, mfa_verified)
    refresh_token = create_refresh_token(user.id, user.tenant_id, user.role, mfa_verified)

    return LoginResult(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        mfa_required=mfa_required,
    )


async def verify_mfa(
    db: AsyncSession,
    token: str,
    code: str,
) -> LoginResult:
    """
    Verify a TOTP code and upgrade a pre-MFA JWT to fully authenticated.
    """
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Not an access token"},
        )

    if payload.get("mfa_verified") is True:
        raise HTTPException(
            status_code=403,
            detail={"code": "MFA_ALREADY_VERIFIED", "message": "MFA already verified"},
        )

    user_id = uuid.UUID(str(payload["sub"]))
    tenant_id = uuid.UUID(str(payload["tenant_id"]))

    user = await _repo.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"},
        )

    if user.totp_secret is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "MFA_NOT_CONFIGURED", "message": "MFA not configured for this user"},
        )

    if not verify_totp(user.totp_secret, code):
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_MFA_CODE", "message": "Invalid verification code"},
        )

    access_token, expires_in = create_access_token(user.id, tenant_id, user.role, mfa_verified=True)
    refresh_token = create_refresh_token(user.id, tenant_id, user.role, mfa_verified=True)

    return LoginResult(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        mfa_required=False,
    )


async def refresh_token(
    db: AsyncSession,
    refresh_token_str: str,
) -> LoginResult:
    """Exchange a valid refresh token for a new access token."""
    try:
        payload = decode_token(refresh_token_str)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired refresh token"},
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Not a refresh token"},
        )

    user_id = uuid.UUID(str(payload["sub"]))
    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    mfa_verified = bool(payload.get("mfa_verified", False))

    user = await _repo.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={"code": "USER_NOT_FOUND", "message": "User not found or inactive"},
        )

    access_token, expires_in = create_access_token(user.id, tenant_id, user.role, mfa_verified)
    new_refresh_token = create_refresh_token(user.id, tenant_id, user.role, mfa_verified)

    return LoginResult(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
        mfa_required=not mfa_verified,
    )


async def require_admin_auth(
    token: str,
    x_tenant_id: str,
) -> AdminContext:
    """
    Validate a Bearer JWT for admin endpoints.

    Raises 401 if token is invalid/expired.
    Raises 403 if mfa_verified is False for privileged roles.
    Raises 403 if tenant_id in token != X-Tenant-ID header.
    """
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Not an access token"},
        )

    user_id = uuid.UUID(str(payload["sub"]))
    token_tenant_id = uuid.UUID(str(payload["tenant_id"]))
    role = str(payload["role"])
    mfa_verified = bool(payload.get("mfa_verified", False))

    # Tenant must match the header
    try:
        header_tenant_id = uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_TENANT_ID", "message": "Invalid X-Tenant-ID"},
        ) from exc

    if token_tenant_id != header_tenant_id:
        raise HTTPException(
            status_code=403,
            detail={"code": "TENANT_MISMATCH", "message": "Token tenant does not match request"},
        )

    # Privileged roles require MFA
    if role in MFA_REQUIRED_ROLES and not mfa_verified:
        raise HTTPException(
            status_code=403,
            detail={"code": "MFA_REQUIRED", "message": "MFA verification required"},
        )

    return AdminContext(
        user_id=user_id,
        tenant_id=token_tenant_id,
        role=role,
        mfa_verified=mfa_verified,
    )
