"""
Orders API endpoints.

GET /orders      — paginated, filterable admin order list (WP-007-BE)
GET /orders/{id} — order detail with lazy notification sync (WP-008-BE)
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.notification_client import NotificationClient
from src.config import settings
from src.dependencies import get_db
from src.repositories.order_repo import OrderRepository
from src.schemas.order import OrderPage, OrderPageMeta, OrderResponse
from src.services.auth_service import AdminContext, require_admin_auth
from src.services.notification_sync import NotificationSyncService

router = APIRouter(tags=["Orders"])

_order_repo = OrderRepository()


async def _get_admin_context(
    authorization: str = Header(...),
    x_tenant_id: str = Header(...),
) -> AdminContext:
    """FastAPI dependency: validate Bearer JWT and return AdminContext."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_TOKEN", "message": "Bearer token required"},
        )
    return await require_admin_auth(token=token, x_tenant_id=x_tenant_id)


def get_notification_client() -> NotificationClient:
    return NotificationClient(base_url=settings.notification_service_url)


@router.get("/orders", response_model=OrderPage)
async def list_orders(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    ctx: AdminContext = Depends(_get_admin_context),
    db: AsyncSession = Depends(get_db),
) -> OrderPage:
    """List orders for the authenticated tenant with optional filters."""
    orders, total = await _order_repo.list_orders(
        db=db,
        tenant_id=ctx.tenant_id,
        status=status,
        q=q,
        page=page,
        per_page=per_page,
    )
    return OrderPage(
        data=[OrderResponse.from_model(order) for order in orders],
        meta=OrderPageMeta(total=total, page=page, per_page=per_page),
    )


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    ctx: AdminContext = Depends(_get_admin_context),
    db: AsyncSession = Depends(get_db),
    notification_client: NotificationClient = Depends(get_notification_client),
) -> OrderResponse:
    """Get a single order by ID with lazy notification status sync."""
    order = await _order_repo.get_by_id(db, order_id, ctx.tenant_id)
    if order is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "ORDER_NOT_FOUND", "message": "Order not found"},
        )
    # Lazy sync notification status (graceful — never raises)
    sync_service = NotificationSyncService(client=notification_client, db=db)
    order = await sync_service.sync_notification_status(order)
    return OrderResponse.from_model(order)
