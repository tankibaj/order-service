"""HTTP client for notification-service."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NotificationReceipt:
    id: uuid.UUID
    status: str
    channel: str | None
    template_id: str | None
    created_at: datetime
    delivered_at: datetime | None


class NotificationClient:
    """Async HTTP client for notification-service."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def send_notification(
        self,
        request: dict[str, object],
        tenant_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """POST /notifications — fire-and-forget after order confirmed.

        Returns the notification_id if successful, None on failure.
        """
        try:
            response = await self._client.post(
                "/notifications",
                json=request,
                headers={"X-Tenant-ID": str(tenant_id)},
            )
            if response.status_code in (200, 201, 202):
                data = response.json()
                notification_id_raw = data.get("id") or data.get("notification_id")
                if notification_id_raw:
                    return uuid.UUID(str(notification_id_raw))
        except Exception:
            logger.warning("Failed to send notification", exc_info=True)
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
        data = response.json()
        return NotificationReceipt(
            id=uuid.UUID(data["id"]),
            status=data["status"],
            channel=data.get("channel"),
            template_id=data.get("template_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            delivered_at=(
                datetime.fromisoformat(data["delivered_at"]) if data.get("delivered_at") else None
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
