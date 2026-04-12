"""Stripe payment client wrapper."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
        # Real implementation would call stripe.PaymentIntent.create(...)
        # For MVP tests this method is mocked via unittest.mock.patch
        raise NotImplementedError(
            "StripeClient.create_payment_intent must be mocked in tests "
            "or replaced with real Stripe SDK calls in production."
        )
