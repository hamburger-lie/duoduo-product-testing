"""Tests for the Redis-based rate limiter (app.core.rate_limit).

Strategy: mock the redis pipeline so we can control the counter value
returned, then verify the dependency raises 429 when the counter
exceeds the limit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db.models.user import User
from app.main import app as main_app

# ------------------------------------------------------------------ #
# Helper: build a patched redis that returns a given counter value
# ------------------------------------------------------------------ #


def _mock_redis_counter(counter: int) -> patch:
    """Return a context-manager patch that makes Redis return ``counter``."""
    pipe_mock = AsyncMock()
    pipe_mock.incr = MagicMock()
    pipe_mock.expire = MagicMock()
    pipe_mock.execute = AsyncMock(return_value=[counter, True])

    client_mock = AsyncMock()
    client_mock.pipeline = MagicMock(return_value=pipe_mock)
    client_mock.aclose = AsyncMock()

    return patch(
        "app.core.rate_limit._get_redis_client",
        return_value=client_mock,
    )


# ------------------------------------------------------------------ #
# Minimal test app that uses the rate limiter directly
# ------------------------------------------------------------------ #


def _make_test_app(tier: str = "gen") -> FastAPI:
    """Tiny app with one endpoint protected by RateLimiter."""
    test_app = FastAPI()
    current_user_dependency = Depends(get_current_user)
    rate_limiter_dependency = Depends(RateLimiter(tier))  # type: ignore[arg-type]

    @test_app.get("/test-endpoint")
    async def endpoint(
        _rl: None = rate_limiter_dependency,
        _user: User = current_user_dependency,
    ) -> dict[str, str]:
        return {"ok": "true"}

    return test_app


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
async def ctx() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    main_app.dependency_overrides[get_db_session] = _override

    async with AsyncClient(
        transport=ASGITransport(app=main_app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory

    main_app.dependency_overrides.clear()
    await engine.dispose()


# ------------------------------------------------------------------ #
# Unit tests for RateLimiter logic (no FastAPI stack needed)
# ------------------------------------------------------------------ #


async def test_rate_limiter_allows_when_under_limit() -> None:
    """Counter = 1 (first request) → no exception raised."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)

    async with session_factory() as session:
        user = User(openid="rl_test_ok", credit_balance=1000)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        limiter = RateLimiter("gen")
        request = MagicMock()

        with _mock_redis_counter(1):
            # Should not raise
            await limiter(request=request, current_user=user)

    await engine.dispose()


async def test_rate_limiter_blocks_when_over_limit() -> None:
    """Counter > limit → AppException with RATE_LIMITED."""
    from app.core.exceptions import AppException

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)

    async with session_factory() as session:
        user = User(openid="rl_test_block", credit_balance=1000)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        limiter = RateLimiter("gen")  # limit = 20
        request = MagicMock()

        with _mock_redis_counter(21):
            with pytest.raises(AppException) as exc_info:
                await limiter(request=request, current_user=user)

        assert exc_info.value.code == "RATE_LIMITED"
        assert exc_info.value.http_status == 429

    await engine.dispose()


async def test_rate_limiter_std_allows_up_to_100() -> None:
    """std tier allows up to 100 req/min."""
    from app.core.exceptions import AppException

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)

    async with session_factory() as session:
        user = User(openid="rl_std_ok", credit_balance=1000)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        limiter = RateLimiter("std")
        request = MagicMock()

        # 100 exactly → ok
        with _mock_redis_counter(100):
            await limiter(request=request, current_user=user)  # no raise

        # 101 → blocked
        with _mock_redis_counter(101), pytest.raises(AppException) as exc_info:
            await limiter(request=request, current_user=user)

        assert exc_info.value.code == "RATE_LIMITED"

    await engine.dispose()


async def test_rate_limiter_fails_open_when_redis_down() -> None:
    """Redis connection error → request is allowed (fail open)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)

    async with session_factory() as session:
        user = User(openid="rl_fail_open", credit_balance=1000)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        limiter = RateLimiter("gen")
        request = MagicMock()

        bad_pipe = MagicMock()
        bad_pipe.incr = MagicMock()
        bad_pipe.expire = MagicMock()
        bad_pipe.execute = AsyncMock(side_effect=ConnectionRefusedError())

        bad_client = AsyncMock()
        bad_client.pipeline = MagicMock(return_value=bad_pipe)

        with patch("app.core.rate_limit._get_redis_client", return_value=bad_client):
            # Should NOT raise even though Redis is down
            await limiter(request=request, current_user=user)

    await engine.dispose()


# ------------------------------------------------------------------ #
# Integration: 429 response via the real ASGI stack
# ------------------------------------------------------------------ #


async def test_rate_limited_api_returns_429(
    ctx: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """When the limiter raises, the API returns 429 with RATE_LIMITED code."""
    client, _ = ctx

    token_resp = await client.post(
        "/api/v1/auth/wechat/login", json={"code": "rl_api_test"}
    )
    token = token_resp.json()["token"]

    # Generate endpoint — patch Redis to return counter = 5 (well under gen limit of 20)
    with _mock_redis_counter(5):
        r = await client.post(
            "/api/v1/surveys/generate",
            json={"evaluation_id": 9999999, "regenerate": False},
            headers={"Authorization": f"Bearer {token}"},
        )
    # Should get a business error (evaluation not found), NOT a rate-limit error
    assert r.status_code != 429

    # Now simulate limit exceeded
    with _mock_redis_counter(999):
        r2 = await client.post(
            "/api/v1/surveys/generate",
            json={"evaluation_id": 9999999, "regenerate": False},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r2.status_code == 429
    body = r2.json()
    assert body["code"] == "RATE_LIMITED"
    assert "retry_after" in body.get("details", {})
