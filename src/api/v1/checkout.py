import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_db, get_tenant_id
from src.models.guest_session import GuestSessionModel
from src.repositories.shipping_method_repo import ShippingMethodRepository
from src.schemas.guest_session import GuestSessionResponse
from src.schemas.shipping_method import ShippingMethodResponse
from src.services.guest_session_service import create_guest_session, validate_guest_session

router = APIRouter()
_shipping_repo = ShippingMethodRepository()


async def require_guest_session(
    x_guest_session_token: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> GuestSessionModel:
    """Validate the X-Guest-Session-Token header and return the active session."""
    return await validate_guest_session(db, x_guest_session_token)


@router.post("/checkout/guest/sessions", status_code=201, response_model=GuestSessionResponse)
async def create_session(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> GuestSessionResponse:
    """Create a new guest checkout session."""
    session = await create_guest_session(db, tenant_id)
    return GuestSessionResponse(
        id=session.id,
        token=session.token,
        expires_at=session.expires_at,
    )


@router.get("/checkout/shipping-methods", response_model=list[ShippingMethodResponse])
async def list_shipping_methods(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[ShippingMethodResponse]:
    """List active shipping methods for the tenant."""
    methods = await _shipping_repo.list_active(db, tenant_id)
    return [
        ShippingMethodResponse(
            id=m.id,
            name=m.name,
            description=m.description,
            cost_minor=m.cost_minor,
            estimated_days_min=m.estimated_days_min,
            estimated_days_max=m.estimated_days_max,
        )
        for m in methods
    ]


@router.post("/checkout/guest/orders", status_code=422)
async def place_guest_order_stub(
    _session: GuestSessionModel = Depends(require_guest_session),
) -> dict[str, Any]:
    """Stub: validates session, returns 422. Full order logic implemented in WP-003-BE."""
    raise HTTPException(
        status_code=422,
        detail={
            "code": "NOT_IMPLEMENTED",
            "message": "Order placement not yet implemented",
        },
    )
