import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from src.api.router import router
from src.config import settings
from src.services.order_saga import StockConflictHTTPException


def _configure_logging() -> None:
    """Set up structured JSON logging to stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=settings.log_level, handlers=[handler], force=True)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Propagate X-Request-ID header through the request/response cycle."""

    async def dispatch(
        self, request: StarletteRequest, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", "")
        response = await call_next(request)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle."""
    _configure_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Order Service",
        version=settings.service_version,
        description="Guest checkout, order management, and admin authentication.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> Response:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": [
                    {
                        "field": ".".join(str(x) for x in err["loc"]),
                        "issue": err["msg"],
                    }
                    for err in exc.errors()
                ],
            },
        )

    @app.exception_handler(StockConflictHTTPException)
    async def stock_conflict_handler(
        request: Request, exc: StockConflictHTTPException
    ) -> JSONResponse:
        """Return a flat 409 StockConflictError (no 'detail' wrapper)."""
        return JSONResponse(status_code=409, content=exc.payload)

    app.include_router(router)

    # Register Prometheus metrics instrumentation
    from src.api.health import setup_metrics

    setup_metrics(app)

    return app


app = create_app()
