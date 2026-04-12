import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.inventory_client import InventoryClient
from src.clients.notification_client import NotificationClient
from src.clients.stripe_client import StripeClient
from src.config import settings
from src.dependencies import get_db, get_tenant_id
from src.models.guest_session import GuestSessionModel
from src.schemas.guest_session import GuestSessionResponse
from src.schemas.order import OrderResponse, PlaceGuestOrderRequest
from src.schemas.shipping_method import ShippingMethodResponse
from src.services.guest_session_service import create_guest_session, validate_guest_session
from src.services.order_saga import OrderSaga

router = APIRouter()


async def require_guest_session(
    x_guest_session_token: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db),
) -> GuestSessionModel:
    """Validate the X-Guest-Session-Token header and return the active session."""
    return await validate_guest_session(db, x_guest_session_token)


def get_inventory_client() -> InventoryClient:
    return InventoryClient(base_url=settings.inventory_service_url)


def get_stripe_client() -> StripeClient:
    return StripeClient(api_key=settings.stripe_api_key)


def get_notification_client() -> NotificationClient:
    return NotificationClient(base_url=settings.notification_service_url)


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
    from src.repositories.shipping_method_repo import ShippingMethodRepository

    repo = ShippingMethodRepository()
    methods = await repo.list_active(db, tenant_id)
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


@router.post("/checkout/guest/orders", status_code=201, response_model=OrderResponse)
async def place_guest_order(
    body: PlaceGuestOrderRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
    session: GuestSessionModel = Depends(require_guest_session),
    inventory_client: InventoryClient = Depends(get_inventory_client),
    stripe_client: StripeClient = Depends(get_stripe_client),
    notification_client: NotificationClient = Depends(get_notification_client),
) -> OrderResponse:
    """Place a guest order via the order saga."""
    saga = OrderSaga(
        inventory_client=inventory_client,
        stripe_client=stripe_client,
        notification_client=notification_client,
    )
    return await saga.place_order(
        db=db,
        request=body,
        guest_session_id=session.id,
        tenant_id=tenant_id,
    )
