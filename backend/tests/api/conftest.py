"""API E2E test fixtures — full black-box testing through HTTP.

Uses in-memory SQLite for speed, but tests the entire request/response
pipeline including middleware, auth, validation, and business logic.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.conversation import Conversation, ConversationMessage
from app.db.models.credit import CreditTransaction
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app


@pytest.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """Full-stack API client with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        for model in [
            User, Product, Persona, Evaluation, Survey, Answer,
            Report, Conversation, ConversationMessage, CreditTransaction,
        ]:
            await conn.run_sync(model.__table__.create)

    # Seed system personas
    async with factory() as session:
        for i, (name, tag) in enumerate([
            ("林雪", "成分党"), ("周曼", "性价比党"), ("张悦", "品牌党"),
        ]):
            session.add(Persona(
                owner_id=None, name=name, avatar="person", age=25 + i,
                gender="female", city="上海", city_tier=1, occupation="白领",
                income_monthly=15000 + i * 5000,
                ocean_o=60, ocean_c=70, ocean_e=50, ocean_a=65, ocean_n=40,
                persona_tag=tag, profile={"bio": f"测试角色{i}"},
                categories=["美妆"], status="active",
            ))
        await session.commit()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient, code: str = "api_test_user") -> dict[str, str]:
    """Login and return auth headers."""
    resp = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}
