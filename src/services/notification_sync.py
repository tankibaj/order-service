"""Lazy notification status sync service.

Fetches fresh notification status from notification-service for orders
whose status is non-terminal (queued or None). Terminal statuses (sent,
delivered, failed) are returned as-is without a network call.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.notification_client import NotificationClient
from src.models.order import OrderModel
from src.repositories.order_repo import OrderRepository

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {"sent", "delivered", "failed"}

_order_repo = OrderRepository()


class NotificationSyncService:
    """Lazily sync notification status for an order from notification-service."""

    def __init__(self, client: NotificationClient, db: AsyncSession) -> None:
        self._client = client
        self._db = db

    async def sync_notification_status(self, order: OrderModel) -> OrderModel:
        """Fetch and cache notification status if not terminal.

        - If notification_id is None → return as-is
        - If status is terminal (sent, delivered, failed) → return as-is
        - Otherwise → fetch from notification-service, update + cache
        - On any error → return order with stale status (never raise)
        """
        if order.notification_id is None:
            return order

        if order.notification_status in _TERMINAL_STATUSES:
            return order

        try:
            assert order.notification_id is not None  # mypy hint
            receipt = await self._client.get_notification(
                notification_id=order.notification_id,
                tenant_id=order.tenant_id,
            )
            order.notification_status = receipt.status
            return await _order_repo.save(self._db, order)
        except Exception:
            logger.warning(
                "Failed to sync notification status",
                exc_info=True,
                extra={"order_id": str(order.id)},
            )
            return order
