from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.db.models import load_all_models
from app.db.models.credit import CreditTransaction
from app.db.models.user import User
from app.db.models.user_activity_event import UserActivityEvent
from app.main import app


@pytest.fixture
async def auth_client() -> AsyncIterator[AsyncClient]:
    load_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(CreditTransaction.__table__.create)
        await connection.run_sync(UserActivityEvent.__table__.create)

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


async def login(client: AsyncClient, code: str = "mock_code_abc") -> dict[str, object]:
    response = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return response.json()


async def test_mock_login_creates_new_user(auth_client: AsyncClient) -> None:
    payload = await login(auth_client)

    assert isinstance(payload["token"], str)
    assert payload["expires_in"] == 604800
    assert payload["user"]["id"].isdigit()
    assert payload["user"]["nickname"] == "未设置"
    assert payload["user"]["role_type"] is None
    assert payload["user"]["credit_balance"] == 1000
    assert payload["user"]["is_new_user"] is True


async def test_mock_login_returns_existing_user(auth_client: AsyncClient) -> None:
    await login(auth_client, code="mock_code_repeat")
    payload = await login(auth_client, code="mock_code_repeat")

    assert payload["user"]["is_new_user"] is False


async def test_mock_login_with_phone_code_stores_phone_number(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/auth/wechat/login",
        json={"code": "mock_phone_user", "phone_code": "mock_phone_code"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["phone_number"] == "13800138000"
    assert payload["user"]["phone_masked"] == "138****8000"

    me = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )
    assert me.status_code == 200
    assert me.json()["phone_masked"] == "138****8000"


async def test_mock_login_accepts_ref_code_from_miniprogram(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/auth/wechat/login",
        json={
            "code": "mock_ref_user",
            "phone_code": "mock_phone_code",
            "ref_code": "7280000000000000",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["phone_masked"] == "138****8000"


async def test_mock_login_without_phone_keeps_existing_phone_number(
    auth_client: AsyncClient,
) -> None:
    first = await auth_client.post(
        "/api/v1/auth/wechat/login",
        json={"code": "same_user_phone", "phone_code": "mock_phone_code"},
    )
    assert first.status_code == 200

    second = await auth_client.post(
        "/api/v1/auth/wechat/login",
        json={"code": "same_user_phone"},
    )
    assert second.status_code == 200
    assert second.json()["user"]["phone_number"] == "13800138000"


async def test_configured_mock_openid_keeps_local_login_stable(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WECHAT_MOCK_OPENID", "mock_openid_local_dev")
    get_settings.cache_clear()
    try:
        first = await login(auth_client, code="devtools_code_one")
        second = await login(auth_client, code="devtools_code_two")
    finally:
        get_settings.cache_clear()

    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["is_new_user"] is False


async def test_empty_mock_login_code_returns_wechat_code_invalid(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post("/api/v1/auth/wechat/login", json={"code": ""})

    assert response.status_code == 400
    assert response.json()["code"] == "WECHAT_CODE_INVALID"


async def test_profile_sets_manufacturer_and_channel(auth_client: AsyncClient) -> None:
    payload = await login(auth_client)
    headers = {"Authorization": f"Bearer {payload['token']}"}

    manufacturer_response = await auth_client.patch(
        "/api/v1/auth/profile",
        json={"role_type": "manufacturer", "nickname": "品牌方"},
        headers=headers,
    )
    assert manufacturer_response.status_code == 200
    assert manufacturer_response.json()["role_type"] == "manufacturer"
    assert manufacturer_response.json()["nickname"] == "品牌方"

    channel_response = await auth_client.patch(
        "/api/v1/auth/profile",
        json={"role_type": "channel"},
        headers=headers,
    )
    assert channel_response.status_code == 200
    assert channel_response.json()["role_type"] == "channel"


async def test_profile_invalid_role_type_returns_invalid_role_type(
    auth_client: AsyncClient,
) -> None:
    payload = await login(auth_client)
    response = await auth_client.patch(
        "/api/v1/auth/profile",
        json={"role_type": "admin"},
        headers={"Authorization": f"Bearer {payload['token']}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ROLE_TYPE"


async def test_me_returns_current_user(auth_client: AsyncClient) -> None:
    payload = await login(auth_client)
    response = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == payload["user"]["id"]


async def test_authenticated_request_records_user_activity(
    auth_client: AsyncClient,
) -> None:
    from sqlalchemy import select

    payload = await login(auth_client, code="mock_activity_user")
    response = await auth_client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {payload['token']}",
            "User-Agent": "activity-test-agent",
            "X-Request-Id": "req_activity_test",
        },
    )

    assert response.status_code == 200

    override = app.dependency_overrides[get_db_session]
    session_gen = override()
    session = await anext(session_gen)
    try:
        events = (await session.scalars(select(UserActivityEvent))).all()
    finally:
        await session_gen.aclose()

    assert len(events) == 1
    assert events[0].user_id == int(str(payload["user"]["id"]))
    assert events[0].event_type == "api_request"
    assert events[0].path == "/api/v1/auth/me"
    assert events[0].method == "GET"
    assert events[0].request_id == "req_activity_test"
    assert events[0].user_agent == "activity-test-agent"


async def test_activity_logging_can_be_disabled(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import select

    monkeypatch.setenv("ACTIVITY_LOG_ENABLED", "false")
    get_settings.cache_clear()
    try:
        payload = await login(auth_client, code="mock_activity_disabled_user")
        response = await auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {payload['token']}"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200

    override = app.dependency_overrides[get_db_session]
    session_gen = override()
    session = await anext(session_gen)
    try:
        events = (await session.scalars(select(UserActivityEvent))).all()
    finally:
        await session_gen.aclose()

    assert events == []


async def test_refresh_returns_new_token(auth_client: AsyncClient) -> None:
    payload = await login(auth_client)
    response = await auth_client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {payload['token']}"},
    )

    assert response.status_code == 200
    assert isinstance(response.json()["token"], str)
    assert response.json()["expires_in"] == 604800


async def test_protected_endpoint_without_token_returns_auth_required(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_auth_endpoints_are_visible_in_openapi(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/auth/wechat/login" in paths
    assert "/api/v1/auth/profile" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/me" in paths


async def test_avatar_upload_rejects_non_image_bytes(auth_client: AsyncClient) -> None:
    payload = await login(auth_client, code="mock_avatar_invalid")
    response = await auth_client.post(
        "/api/v1/auth/avatar",
        headers={"Authorization": f"Bearer {payload['token']}"},
        files={"file": ("avatar.jpg", b"<html>not an image</html>", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_FILE_TYPE"


async def test_avatar_upload_rejects_oversized_image(auth_client: AsyncClient) -> None:
    payload = await login(auth_client, code="mock_avatar_large")
    response = await auth_client.post(
        "/api/v1/auth/avatar",
        headers={"Authorization": f"Bearer {payload['token']}"},
        files={
            "file": (
                "avatar.jpg",
                b"\xff\xd8\xff\xe0" + b"\x00" * (2 * 1024 * 1024 + 1),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "FILE_TOO_LARGE"
