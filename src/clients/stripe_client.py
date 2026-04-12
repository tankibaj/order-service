"""Stripe payment client wrapper."""

import logging
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# When set to this placeholder, the client runs in dev/test mode and
# auto-approves all payments without calling the real Stripe API.
_DEV_KEY = "sk_test_placeholder"


class PaymentError(Exception):
    """Raised when payment capture fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class PaymentIntent:
    id: str
    status: str


class StripeClient:
    """Wrapper around Stripe payment intent creation.

    In production, this would call the Stripe API directly.
    For testing, the create_payment_intent method is mocked.
    When STRIPE_API_KEY=sk_test_placeholder the client auto-approves payments
    (dev/local mode only).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def create_payment_intent(
        self,
        token: str,
        amount: int,
        currency: str = "gbp",
    ) -> PaymentIntent:
        """Create and capture a Stripe PaymentIntent.

        Raises PaymentError on failure (declined, network error, etc.).
        """
        if self._api_key == _DEV_KEY:
            # Dev/local mode — return a synthetic successful intent so the
            # full order saga can be exercised without a real Stripe account.
            logger.info("Stripe dev-mode: auto-approving payment of %d %s", amount, currency)
            return PaymentIntent(id=f"pi_dev_{uuid.uuid4().hex}", status="succeeded")

        # Real implementation would call stripe.PaymentIntent.create(...)
        # For MVP tests this method is mocked via unittest.mock.patch
        raise NotImplementedError(
            "StripeClient.create_payment_intent must be mocked in tests "
            "or replaced with real Stripe SDK calls in production."
        )
