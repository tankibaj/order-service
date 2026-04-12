"""HTTP client for notification-service."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NotificationLineItem:
    """A single order line in the notification payload."""

    product_name: str
    quantity: int
    unit_price: str  # formatted, e.g. "$29.99"


@dataclass
class OrderConfirmationPayload:
    """Payload for an order_confirmation notification."""

    order_reference: str
    lines: list[NotificationLineItem]
    total: str  # formatted, e.g. "$74.97"


@dataclass
class SendOrderConfirmationRequest:
    """Typed request object for POST /notifications (order_confirmation template)."""

    recipient_address: str
    payload: OrderConfirmationPayload


@dataclass
class NotificationReceipt:
    """Response from POST /notifications."""

    id: uuid.UUID
    status: str = "queued"
    channel: str | None = None
    template_id: str | None = None
    created_at: datetime | None = None
    delivered_at: datetime | None = None


def _parse_receipt(data: dict[str, object]) -> NotificationReceipt:
    """Parse a notification receipt from a raw JSON dict."""
    raw_id = data.get("id")
    if not raw_id:
        raise ValueError("Notification receipt missing 'id'")

    created_raw = data.get("created_at")
    delivered_raw = data.get("delivered_at")
    return NotificationReceipt(
        id=uuid.UUID(str(raw_id)),
        status=str(data.get("status", "queued")),
        channel=str(data["channel"]) if data.get("channel") else None,
        template_id=str(data["template_id"]) if data.get("template_id") else None,
        created_at=datetime.fromisoformat(str(created_raw)) if created_raw else None,
        delivered_at=datetime.fromisoformat(str(delivered_raw)) if delivered_raw else None,
    )


class NotificationClient:
    """Async HTTP client for notification-service."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def send_order_confirmation(
        self,
        request: SendOrderConfirmationRequest,
        tenant_id: uuid.UUID,
    ) -> NotificationReceipt | None:
        """POST /notifications with order_confirmation template.

        Builds the contract-compliant payload and dispatches the notification.
        Returns a ``NotificationReceipt`` on 2xx, or ``None`` on any failure.
        No PII (email address) is written to logs.
        """
        payload = {
            "channel": "email",
            "template_id": "order_confirmation",
            "recipient": {"address": request.recipient_address},
            "payload": {
                "order_reference": request.payload.order_reference,
                "lines": [
                    {
                        "product_name": line.product_name,
                        "quantity": line.quantity,
                        "unit_price": line.unit_price,
                    }
                    for line in request.payload.lines
                ],
                "total": request.payload.total,
            },
        }
        try:
            response = await self._client.post(
                "/notifications",
                json=payload,
                headers={"X-Tenant-ID": str(tenant_id)},
            )
            response.raise_for_status()
            return _parse_receipt(response.json())
        except httpx.HTTPError:
            logger.warning(
                "Failed to dispatch order confirmation notification",
                extra={"order_reference": request.payload.order_reference},
            )
            return None

    async def get_notification(
        self,
        notification_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> NotificationReceipt:
        """GET /notifications/{notificationId} — fetch notification status."""
        response = await self._client.get(
            f"/notifications/{notification_id}",
            headers={"X-Tenant-ID": str(tenant_id)},
        )
        response.raise_for_status()
        return _parse_receipt(response.json())

    async def aclose(self) -> None:
        await self._client.aclose()
