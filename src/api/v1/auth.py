import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_db, get_tenant_id
from src.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MfaVerifyRequest,
    MfaVerifyResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
)
from src.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
async def admin_login(
    body: LoginRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate an admin user and return a JWT."""
    result = await auth_service.login(
        db=db,
        email=body.email,
        password=body.password,
        tenant_id=tenant_id,
    )
    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="Bearer",
        expires_in=result.expires_in,
        mfa_required=result.mfa_required,
    )


@router.post("/mfa/verify", response_model=MfaVerifyResponse)
async def verify_mfa(
    body: MfaVerifyRequest,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> MfaVerifyResponse:
    """Verify TOTP code and upgrade pre-MFA JWT to fully authenticated JWT."""
    # Extract Bearer token
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Bearer token required"},
        )

    result = await auth_service.verify_mfa(db=db, token=token, code=body.code)
    return MfaVerifyResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="Bearer",
        expires_in=result.expires_in,
    )


@router.post("/token/refresh", response_model=TokenRefreshResponse)
async def token_refresh(
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenRefreshResponse:
    """Refresh an access token using a valid refresh token."""
    result = await auth_service.refresh_token(db=db, refresh_token_str=body.refresh_token)
    return TokenRefreshResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="Bearer",
        expires_in=result.expires_in,
    )
