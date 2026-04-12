import uuid
from datetime import datetime

from pydantic import BaseModel


class GuestSessionResponse(BaseModel):
    id: uuid.UUID
    token: str
    expires_at: datetime
