"""
Integration tests for observability endpoints — WP-003-BE verification.

Covers TS-001-059, TS-001-060, TS-001-061.
"""

from httpx import AsyncClient


async def test_ts_001_059_health_returns_200(client: AsyncClient) -> None:
    """TS-001-059: GET /health returns 200 with ok status."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "order-service"


async def test_ts_001_060_ready_returns_200(client: AsyncClient) -> None:
    """TS-001-060: GET /ready returns 200 when database is healthy."""
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_ts_001_061_metrics_returns_prometheus_format(client: AsyncClient) -> None:
    """TS-001-061: GET /metrics returns Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text or "python_info" in response.text
