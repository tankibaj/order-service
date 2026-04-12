"""
Integration tests for observability endpoints.

Covers /health, /ready, /metrics.
"""

from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health returns 200 with expected JSON body."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "order-service"
    assert "version" in body


async def test_ready_returns_200_when_db_healthy(client: AsyncClient) -> None:
    """GET /ready returns 200 when database is reachable."""
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_metrics_endpoint_accessible(client: AsyncClient) -> None:
    """GET /metrics returns Prometheus-format metrics."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text or "python_info" in response.text
