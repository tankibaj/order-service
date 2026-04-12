from pydantic import BaseModel


class ErrorDetail(BaseModel):
    field: str | None = None
    issue: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
