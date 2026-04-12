"""Health, readiness, and metrics endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.dependencies import get_db

router = APIRouter(tags=["Observability"])


@router.get("/health")
async def health() -> JSONResponse:
    """Liveness probe — returns 200 if the service is running."""
    return JSONResponse(
        content={
            "status": "ok",
            "service": "order-service",
            "version": settings.service_version,
        }
    )


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness probe — checks database connectivity."""
    try:
        await session.execute(text("SELECT 1"))
        return JSONResponse(
            content={"status": "ok", "database": "ok"},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": str(exc)},
        )


def setup_metrics(app: object) -> None:
    """Register Prometheus metrics instrumentation on the FastAPI app."""
    from fastapi import FastAPI

    if isinstance(app, FastAPI):
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")
