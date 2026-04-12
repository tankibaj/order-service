"""Order placement saga: validate → reserve → capture → deduct → persist → notify."""

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.inventory_client import InventoryClient, StockConflictError
from src.clients.notification_client import NotificationClient
from src.clients.stripe_client import PaymentError, StripeClient
from src.repositories.order_repo import CreateOrderData, CreateOrderLineData, OrderRepository
from src.repositories.shipping_method_repo import ShippingMethodRepository
from src.schemas.common import StockConflictErrorResponse, StockConflictItem
from src.schemas.order import OrderResponse, PlaceGuestOrderRequest
from src.services.reference_generator import generate_unique_reference


class StockConflictHTTPException(Exception):
    """Raised when inventory-service returns a 409 stock conflict.

    Handled by a registered exception handler that returns the contract-compliant
    StockConflictError response (flat JSON, no 'detail' wrapper).
    """

    def __init__(self, payload: dict) -> None:  # type: ignore[type-arg]
        self.payload = payload


logger = logging.getLogger(__name__)

_UNIT_PRICE_MVP = 100  # 100 pence placeholder; real price lookup deferred

_order_repo = OrderRepository()
_shipping_repo = ShippingMethodRepository()


class OrderSaga:
    """Orchestrate the guest order placement saga."""

    def __init__(
        self,
        inventory_client: InventoryClient,
        stripe_client: StripeClient,
        notification_client: NotificationClient,
    ) -> None:
        self._inventory = inventory_client
        self._stripe = stripe_client
        self._notifications = notification_client

    async def place_order(
        self,
        db: AsyncSession,
        request: PlaceGuestOrderRequest,
        guest_session_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> OrderResponse:
        """Execute the order placement saga.

        Steps:
        1. Validate shipping method exists
        2. Reserve stock (inventory-service)
        3. Capture payment (Stripe)  — on failure: release reservation
        4. Deduct stock (inventory-service)
        5. Persist Order + OrderLines
        6. Dispatch notification (fire-and-forget)
        7. Return confirmed Order
        """
        # ── Step 1: Validate shipping method ─────────────────────────────
        shipping_method = await _shipping_repo.get_by_id(db, request.shipping_method_id, tenant_id)
        if shipping_method is None or not shipping_method.is_active:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_SHIPPING_METHOD",
                    "message": "Shipping method not found or inactive",
                },
            )

        # ── Step 2: Reserve stock ─────────────────────────────────────────
        order_id = uuid.uuid4()
        lines_payload = [
            {"sku_id": line.sku_id, "quantity": line.quantity} for line in request.lines
        ]

        try:
            reservation = await self._inventory.reserve_stock(
                order_id=order_id,
                lines=lines_payload,
                tenant_id=tenant_id,
            )
        except StockConflictError as exc:
            raise StockConflictHTTPException(
                payload=StockConflictErrorResponse(
                    code="STOCK_CONFLICT",
                    message=exc.message,
                    conflicts=[
                        StockConflictItem(
                            sku_id=c.sku_id,
                            requested=c.requested,
                            available=c.available,
                        )
                        for c in exc.conflicts
                    ],
                ).model_dump(mode="json"),
            ) from exc

        # ── Step 3: Capture payment ───────────────────────────────────────
        subtotal_minor = sum(line.quantity * _UNIT_PRICE_MVP for line in request.lines)
        shipping_cost_minor = shipping_method.cost_minor
        total_minor = subtotal_minor + shipping_cost_minor

        try:
            payment_intent = await self._stripe.create_payment_intent(
                token=request.payment_method.token,
                amount=total_minor,
                currency="gbp",
            )
        except PaymentError as exc:
            # Compensate: release the stock reservation
            await self._inventory.release_reservation(
                reservation_id=reservation.reservation_id,
                tenant_id=tenant_id,
            )
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "PAYMENT_FAILED",
                    "message": exc.message,
                },
            ) from exc
        except Exception as exc:
            # Unexpected payment error — still compensate
            await self._inventory.release_reservation(
                reservation_id=reservation.reservation_id,
                tenant_id=tenant_id,
            )
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "PAYMENT_FAILED",
                    "message": "Payment capture failed",
                },
            ) from exc

        # ── Step 4: Deduct stock ──────────────────────────────────────────
        await self._inventory.deduct_stock(
            reservation_id=reservation.reservation_id,
            tenant_id=tenant_id,
        )

        # ── Step 5: Persist order ─────────────────────────────────────────
        reference = await generate_unique_reference(db, tenant_id)
        line_data = [
            CreateOrderLineData(
                sku_id=line.sku_id,
                product_name="Product",
                variant_label="Standard",
                quantity=line.quantity,
                unit_price_minor=_UNIT_PRICE_MVP,
                subtotal_minor=line.quantity * _UNIT_PRICE_MVP,
            )
            for line in request.lines
        ]
        order_data = CreateOrderData(
            tenant_id=tenant_id,
            reference=reference,
            status="confirmed",
            guest_email=str(request.email),
            customer_id=None,
            shipping_address=request.shipping_address.model_dump(),
            shipping_method_id=request.shipping_method_id,
            shipping_cost_minor=shipping_cost_minor,
            subtotal_minor=subtotal_minor,
            tax_minor=0,
            total_minor=total_minor,
            payment_intent_id=payment_intent.id,
            idempotency_key=None,
            notification_id=None,
            notification_status=None,
            lines=line_data,
        )
        order = await _order_repo.create(db, order_data)

        # ── Step 6: Dispatch notification (fire-and-forget) ───────────────
        notification_payload: dict[str, object] = {
            "type": "order_confirmation",
            "recipient": str(request.email),
            "order_id": str(order.id),
            "reference": reference,
        }
        notification_id = await self._notifications.send_notification(
            request=notification_payload,
            tenant_id=tenant_id,
        )
        if notification_id is not None:
            order.notification_id = notification_id
            order.notification_status = "queued"
            await _order_repo.save(db, order)

        return OrderResponse.from_model(order)
