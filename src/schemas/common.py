"""Shared Pydantic schemas used across multiple endpoints."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class Address(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    postal_code: str
    country_code: str = Field(min_length=2, max_length=2)


class PaymentMethodInput(BaseModel):
    type: Literal["card", "digital_wallet"]
    token: str = Field(min_length=1)


class StockConflictItem(BaseModel):
    sku_id: uuid.UUID
    requested: int
    available: int


class StockConflictErrorResponse(BaseModel):
    code: str = "STOCK_CONFLICT"
    message: str
    conflicts: list[StockConflictItem]
