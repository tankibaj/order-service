"""Request validation helpers.

Provides contract-compliant 422 error formatting for Pydantic validation
errors raised during FastAPI request parsing. Used by the global exception
handler registered in ``src/main.py``.

Validation rules are enforced at the Pydantic model layer (see
``src/schemas/order.py`` and ``src/schemas/common.py``). This module handles
the *formatting* of those errors into the ErrorResponse contract shape:

    {
        "code": "VALIDATION_ERROR",
        "message": "...",
        "details": [{"field": "<dot.path>", "issue": "<message>"}, ...]
    }
"""

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def build_validation_error_response(exc: RequestValidationError) -> JSONResponse:
    """Build a 422 ``JSONResponse`` from a ``RequestValidationError``.

    Strips the leading ``body`` segment from each error's location so that
    field paths read as ``shipping_address.postal_code`` rather than
    ``body.shipping_address.postal_code``.
    """
    details = []
    for err in exc.errors():
        loc_parts = [str(p) for p in err["loc"] if p != "body"]
        details.append(
            {
                "field": ".".join(loc_parts),
                "issue": err["msg"],
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": details,
        },
    )
