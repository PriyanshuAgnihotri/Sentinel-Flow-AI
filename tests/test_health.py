from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def no_redis(monkeypatch):
    monkeypatch.setattr(app.state, "redis", None, raising=False)
    monkeypatch.setattr(app.state, "cache", None, raising=False)


@pytest.mark.asyncio
async def test_health_endpoint_is_live():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_succeeds_when_database_is_up_and_redis_is_optional(monkeypatch, no_redis):
    monkeypatch.setattr("app.main.database_is_available", AsyncMock(return_value=True))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": True,
        "redis": False,
        "cache_enabled": False,
    }


@pytest.mark.asyncio
async def test_readiness_returns_503_when_database_is_down(monkeypatch, no_redis):
    monkeypatch.setattr("app.main.database_is_available", AsyncMock(return_value=False))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["database"] is False


@pytest.mark.asyncio
async def test_metrics_requires_bearer_token():
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required."


@pytest.mark.asyncio
async def test_metrics_rejects_invalid_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "metrics_api_token", "correct-test-token")

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer incorrect-test-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid metrics bearer token."


@pytest.mark.asyncio
async def test_metrics_accepts_valid_bearer_token(monkeypatch):
    monkeypatch.setattr(settings, "metrics_api_token", "correct-test-token")

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer correct-test-token"},
        )

    assert response.status_code == 200
    assert isinstance(response.json(), dict)


@pytest.mark.asyncio
async def test_metrics_returns_503_when_token_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "metrics_api_token", "")

    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/metrics",
            headers={"Authorization": "Bearer some-test-token"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Metrics authentication is not configured."
