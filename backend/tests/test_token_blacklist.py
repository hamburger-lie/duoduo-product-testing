from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models import load_all_models
from app.db.models.user import User
from app.main import app


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expires: dict[str, int] = {}
        self.closed = False

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        self.values[key] = value
        self.expires[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def aclose(self) -> None:
        self.closed = True


def _non_testing_settings() -> SimpleNamespace:
    return SimpleNamespace(app_env="development", redis_url="redis://test/0")


@pytest.fixture
async def auth_client() -> AsyncIterator[AsyncClient]:
    load_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_blacklist_and_check() -> None:
    from app.core import token_blacklist

    fake_redis = _FakeRedis()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)

    with (
        patch("app.core.token_blacklist.get_settings", return_value=_non_testing_settings()),
        patch("app.core.token_blacklist._get_redis_client", return_value=fake_redis),
    ):
        await token_blacklist.blacklist_token("jti-1", expires_at)
        assert await token_blacklist.is_blacklisted("jti-1") is True

    assert fake_redis.values["bl:jti-1"] == "1"
    assert fake_redis.expires["bl:jti-1"] > 0
    assert fake_redis.closed is True


async def test_not_blacklisted() -> None:
    from app.core import token_blacklist

    with (
        patch("app.core.token_blacklist.get_settings", return_value=_non_testing_settings()),
        patch("app.core.token_blacklist._get_redis_client", return_value=_FakeRedis()),
    ):
        assert await token_blacklist.is_blacklisted("missing-jti") is False


async def test_redis_unavailable_fail_open() -> None:
    from app.core import token_blacklist

    with (
        patch("app.core.token_blacklist.get_settings", return_value=_non_testing_settings()),
        patch(
            "app.core.token_blacklist._get_redis_client",
            side_effect=ConnectionError("redis down"),
        ),
    ):
        await token_blacklist.blacklist_token(
            "jti-2",
            datetime.now(UTC) + timedelta(minutes=5),
        )
        assert await token_blacklist.is_blacklisted("jti-2") is False


async def test_logout_invalidates_token(auth_client: AsyncClient) -> None:
    fake_redis = _FakeRedis()

    login_response = await auth_client.post(
        "/api/v1/auth/wechat/login",
        json={"code": "logout_invalidates_token"},
    )
    assert login_response.status_code == 200
    token = str(login_response.json()["token"])
    headers = {"Authorization": f"Bearer {token}"}

    with (
        patch("app.core.token_blacklist.get_settings", return_value=_non_testing_settings()),
        patch("app.core.token_blacklist._get_redis_client", return_value=fake_redis),
    ):
        logout_response = await auth_client.post("/api/v1/auth/logout", headers=headers)
        assert logout_response.status_code == 200
        assert logout_response.json() == {"message": "ok"}

        me_response = await auth_client.get("/api/v1/auth/me", headers=headers)

    assert me_response.status_code == 401
