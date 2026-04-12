"""Shared Pydantic schemas used across multiple endpoints."""

import uuid

from pydantic import BaseModel


class Address(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    postal_code: str
    country_code: str


class PaymentMethodInput(BaseModel):
    type: str  # "card" | "digital_wallet"
    token: str


class StockConflictItem(BaseModel):
    sku_id: uuid.UUID
    requested: int
    available: int


class StockConflictErrorResponse(BaseModel):
    code: str = "STOCK_CONFLICT"
    message: str
    conflicts: list[StockConflictItem]
