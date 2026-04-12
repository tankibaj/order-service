"""HTTP client for inventory-service stock operations."""

import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx
from fastapi import HTTPException


@dataclass
class ReserveStockResponse:
    reservation_id: uuid.UUID
    expires_at: datetime


@dataclass
class StockConflict:
    sku_id: uuid.UUID
    requested: int
    available: int


class StockConflictError(Exception):
    """Raised when inventory-service returns 409 STOCK_CONFLICT."""

    def __init__(self, message: str, conflicts: list[StockConflict]) -> None:
        super().__init__(message)
        self.message = message
        self.conflicts = conflicts


class InventoryClient:
    """Async HTTP client for inventory-service."""

    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def reserve_stock(
        self,
        order_id: uuid.UUID,
        lines: list[dict[str, object]],
        tenant_id: uuid.UUID,
    ) -> ReserveStockResponse:
        """POST /stock/reserve — reserve stock for an order.

        Raises StockConflictError on 409, HTTPException on other errors.
        """
        payload = {
            "order_id": str(order_id),
            "lines": [
                {"sku_id": str(line["sku_id"]), "quantity": line["quantity"]} for line in lines
            ],
        }
        response = await self._client.post(
            "/stock/reserve",
            json=payload,
            headers={"X-Tenant-ID": str(tenant_id)},
        )
        if response.status_code == 409:
            body = response.json()
            conflicts = [
                StockConflict(
                    sku_id=uuid.UUID(c["sku_id"]),
                    requested=c["requested"],
                    available=c["available"],
                )
                for c in body.get("conflicts", [])
            ]
            raise StockConflictError(
                message=body.get("message", "Insufficient stock"),
                conflicts=conflicts,
            )
        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "INVENTORY_ERROR",
                    "message": f"Inventory service error: {response.status_code}",
                },
            )
        data = response.json()
        return ReserveStockResponse(
            reservation_id=uuid.UUID(data["reservation_id"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )

    async def deduct_stock(
        self,
        reservation_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        """POST /stock/deduct — deduct stock using a reservation."""
        payload = {"reservation_id": str(reservation_id)}
        response = await self._client.post(
            "/stock/deduct",
            json=payload,
            headers={"X-Tenant-ID": str(tenant_id)},
        )
        if response.status_code not in (200, 204):
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "INVENTORY_ERROR",
                    "message": f"Inventory deduct error: {response.status_code}",
                },
            )

    async def release_reservation(
        self,
        reservation_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        """POST /stock/reservations/{id}/release — compensate a failed payment."""
        response = await self._client.post(
            f"/stock/reservations/{reservation_id}/release",
            headers={"X-Tenant-ID": str(tenant_id)},
        )
        # Best-effort: log but do not raise on failure
        if response.status_code not in (200, 204):
            import logging

            logging.getLogger(__name__).warning(
                "Failed to release stock reservation",
                extra={
                    "reservation_id": str(reservation_id),
                    "status_code": response.status_code,
                },
            )

    async def aclose(self) -> None:
        await self._client.aclose()
