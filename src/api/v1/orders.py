"""
Orders stub endpoint.

GET /orders is implemented as a stub that validates admin auth and returns
an empty list. Full order retrieval logic is implemented in WP-007-BE.
"""

from fastapi import APIRouter, Depends, Header

from src.services.auth_service import AdminContext, require_admin_auth

router = APIRouter(tags=["Orders"])


async def _get_admin_context(
    authorization: str = Header(...),
    x_tenant_id: str = Header(...),
) -> AdminContext:
    """FastAPI dependency: validate Bearer JWT and return AdminContext."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Bearer token required"},
        )
    return await require_admin_auth(token=token, x_tenant_id=x_tenant_id)


@router.get("/orders", response_model=list[dict])  # type: ignore[type-arg]
async def list_orders_stub(
    _ctx: AdminContext = Depends(_get_admin_context),
) -> list[dict]:  # type: ignore[type-arg]
    """Stub: validates admin auth, returns empty list. Full logic in WP-007-BE."""
    return []
