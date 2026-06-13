from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from app.core import security
from app.core.config import get_settings
from app.core.security import create_access_token


class _FakeCache:
    def __init__(self, value: dict[str, object] | None = None) -> None:
        self.value = value
        self.get = AsyncMock(return_value=(value is not None, value))
        self.set = AsyncMock()


def _request(method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/v1/auth/me",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
        }
    )


def _cached_user_payload(user_id: int = 123) -> dict[str, object]:
    return {
        "id": user_id,
        "openid": "cached-openid",
        "unionid": None,
        "phone_number": "13800138000",
        "nickname": "缓存用户",
        "avatar_url": None,
        "role_type": "manufacturer",
        "credit_balance": 888,
        "status": "active",
        "is_plus": False,
    }


async def test_get_current_user_uses_cache_for_safe_requests(
    monkeypatch,
) -> None:
    token, _ = create_access_token(user_id=123)
    cache = _FakeCache(_cached_user_payload())
    repo_get = AsyncMock()
    activity = AsyncMock()

    monkeypatch.setenv("CURRENT_USER_CACHE_TTL_SECONDS", "300")
    get_settings.cache_clear()
    monkeypatch.setattr(security, "current_user_cache", cache)
    monkeypatch.setattr(security.token_blacklist, "is_blacklisted", AsyncMock(return_value=False))
    monkeypatch.setattr(security.UserRepository, "get_by_id", repo_get)
    monkeypatch.setattr(security, "_record_user_activity", activity)

    try:
        user = await security.get_current_user(
            request=_request("GET"),
            token=token,
            session=SimpleNamespace(),
        )
    finally:
        get_settings.cache_clear()

    assert user.id == 123
    assert user.nickname == "缓存用户"
    repo_get.assert_not_awaited()
    activity.assert_awaited_once()


async def test_get_current_user_bypasses_cache_for_writes(
    monkeypatch,
) -> None:
    token, _ = create_access_token(user_id=123)
    cache = _FakeCache(_cached_user_payload())
    db_user = security.User(
        id=123,
        openid="db-openid",
        nickname="数据库用户",
        credit_balance=1000,
        status="active",
    )
    repo_get = AsyncMock(return_value=db_user)

    monkeypatch.setenv("CURRENT_USER_CACHE_TTL_SECONDS", "300")
    get_settings.cache_clear()
    monkeypatch.setattr(security, "current_user_cache", cache)
    monkeypatch.setattr(security.token_blacklist, "is_blacklisted", AsyncMock(return_value=False))
    monkeypatch.setattr(security.UserRepository, "get_by_id", repo_get)
    monkeypatch.setattr(security, "_record_user_activity", AsyncMock())

    try:
        user = await security.get_current_user(
            request=_request("POST"),
            token=token,
            session=SimpleNamespace(),
        )
    finally:
        get_settings.cache_clear()

    assert user.nickname == "数据库用户"
    cache.get.assert_not_awaited()
    repo_get.assert_awaited_once_with(123)
