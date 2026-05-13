from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.main import app


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _mock_redis_ok() -> patch:
    """Patch redis.asyncio.from_url so PING succeeds."""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.aclose = AsyncMock()
    return patch("app.services.health_service.aioredis.from_url", return_value=mock_client)


def _mock_redis_fail() -> patch:
    """Patch redis.asyncio.from_url so PING raises."""
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(side_effect=ConnectionRefusedError("redis down"))
    mock_client.aclose = AsyncMock()
    return patch("app.services.health_service.aioredis.from_url", return_value=mock_client)


def _mock_qdrant_ok() -> patch:
    """Patch httpx.AsyncClient so Qdrant /healthz returns 200."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    return patch("app.services.health_service.httpx.AsyncClient", return_value=mock_http)


def _mock_qdrant_fail() -> patch:
    """Patch httpx.AsyncClient so Qdrant /healthz raises."""
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=ConnectionRefusedError("qdrant down"))
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    return patch("app.services.health_service.httpx.AsyncClient", return_value=mock_http)


async def _make_ready_client() -> tuple[AsyncClient, async_sessionmaker[AsyncSession]]:
    """Return an ASGI test client with an in-memory SQLite DB wired in."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver"), engine


# ------------------------------------------------------------------ #
# Tests — /health and /health/live (no external deps)
# ------------------------------------------------------------------ #


async def test_health_returns_service_status() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "duoduo-product-testing-api",
        "version": "0.1.0",
    }


async def test_health_live_returns_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ------------------------------------------------------------------ #
# Tests — /health/ready (all checks mocked)
# ------------------------------------------------------------------ #


async def test_health_ready_all_ok() -> None:
    """All three dependencies healthy → 200 with all checks 'ok'."""
    client, engine = await _make_ready_client()
    try:
        with _mock_redis_ok(), _mock_qdrant_ok():
            async with client as c:
                response = await c.get("/health/ready")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["qdrant"] == "ok"


async def test_health_ready_redis_failure_returns_503() -> None:
    """Redis down → 503 with redis=failed."""
    client, engine = await _make_ready_client()
    try:
        with _mock_redis_fail(), _mock_qdrant_ok():
            async with client as c:
                response = await c.get("/health/ready")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert body["details"]["redis"] == "failed"
    assert body["details"]["database"] == "ok"


async def test_health_ready_qdrant_failure_returns_503() -> None:
    """Qdrant down → 503 with qdrant=failed."""
    client, engine = await _make_ready_client()
    try:
        with _mock_redis_ok(), _mock_qdrant_fail():
            async with client as c:
                response = await c.get("/health/ready")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert response.status_code == 503
    body = response.json()
    assert body["details"]["qdrant"] == "failed"
    assert body["details"]["redis"] == "ok"


async def test_health_ready_db_failure_returns_503() -> None:
    """Database down → 503 with database=failed."""
    # Use a bad connection string to force a DB failure
    bad_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    bad_session_factory = async_sessionmaker(bad_engine, expire_on_commit=False)

    async def bad_override() -> AsyncGenerator[AsyncSession, None]:
        async with bad_session_factory() as session:
            # Patch execute to raise
            from unittest.mock import AsyncMock as AM
            session.execute = AM(side_effect=Exception("DB down"))  # type: ignore[method-assign]
            yield session

    app.dependency_overrides[get_db_session] = bad_override

    with _mock_redis_ok(), _mock_qdrant_ok():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as c:
            response = await c.get("/health/ready")

    app.dependency_overrides.clear()
    await bad_engine.dispose()

    assert response.status_code == 503
    body = response.json()
    assert body["details"]["database"] == "failed"


# ------------------------------------------------------------------ #
# Tests — OpenAPI visibility
# ------------------------------------------------------------------ #


async def test_health_endpoints_are_visible_in_openapi() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/openapi.json")
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths
