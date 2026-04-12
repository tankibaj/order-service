"""Human-readable order reference generator.

Format: ORD-YYYYMMDD-XXXX where XXXX is 4 uppercase alphanumeric characters.
Example: ORD-20260412-A3K9
"""

import secrets
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.order_repo import OrderRepository

_repo = OrderRepository()
_MAX_RETRIES = 3


def _generate_suffix() -> str:
    """Generate a 4-character uppercase alphanumeric suffix."""
    return secrets.token_hex(2).upper()


def _build_reference(suffix: str) -> str:
    today = date.today().strftime("%Y%m%d")
    return f"ORD-{today}-{suffix}"


async def generate_unique_reference(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> str:
    """Generate a unique order reference for the given tenant.

    Retries up to 3 times on collision (extremely rare in practice).
    Raises RuntimeError if all attempts collide.
    """
    for _ in range(_MAX_RETRIES):
        suffix = _generate_suffix()
        reference = _build_reference(suffix)
        exists = await _repo.reference_exists(db, tenant_id, reference)
        if not exists:
            return reference
    raise RuntimeError(f"Failed to generate unique order reference after {_MAX_RETRIES} attempts")
