from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from src.api.router import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle."""
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Order Service",
        version="0.1.0",
        description="Guest checkout, order management, and admin authentication.",
        lifespan=lifespan,
    )

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

    app.include_router(router)
    return app


app = create_app()
