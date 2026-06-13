from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.core.security import create_access_token
from app.db.models.customize_request import CustomizeRequest
from app.db.models.user import User
from app.main import app


@pytest.fixture
async def customize_context() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(CustomizeRequest.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    await engine.dispose()


async def _create_token(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        user = User(
            openid="customize_openid",
            nickname="customize-user",
            credit_balance=50,
            status="active",
        )
        session.add(user)
        await session.commit()
        return create_access_token(user_id=user.id)[0]


def _valid_payload() -> dict[str, str]:
    return {
        "name": "张三",
        "phone": "13800138000",
        "company": "测试公司",
        "requirement": "需要定制测评服务",
    }


async def test_customize_submit_requires_authentication(
    customize_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, _ = customize_context

    response = await client.post("/api/v1/customize/submit", json=_valid_payload())

    assert response.status_code == 401


async def test_customize_submit_rejects_invalid_phone(
    customize_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_factory = customize_context
    token = await _create_token(session_factory)
    payload = _valid_payload()
    payload["phone"] = "12345"

    response = await client.post(
        "/api/v1/customize/submit",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_customize_submit_rejects_overlong_requirement(
    customize_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_factory = customize_context
    token = await _create_token(session_factory)
    payload = _valid_payload()
    payload["requirement"] = "x" * 2001

    response = await client.post(
        "/api/v1/customize/submit",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_customize_submit_persists_authenticated_user_request(
    customize_context: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, session_factory = customize_context
    token = await _create_token(session_factory)

    response = await client.post(
        "/api/v1/customize/submit",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "pytest-client"},
        json=_valid_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}

    async with session_factory() as session:
        row = (await session.execute(select(CustomizeRequest))).scalar_one()

    assert row.user_id > 0
    assert row.name == "张三"
    assert row.phone == "13800138000"
    assert row.company == "测试公司"
    assert row.requirement == "需要定制测评服务"
    assert row.status == "submitted"
    assert row.user_agent == "pytest-client"
