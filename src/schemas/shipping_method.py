import uuid

from pydantic import BaseModel


class ShippingMethodResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    cost_minor: int
    estimated_days_min: int | None = None
    estimated_days_max: int | None = None
