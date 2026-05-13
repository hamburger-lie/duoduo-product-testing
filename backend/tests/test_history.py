from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@dataclass
class HistoryContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def ctx() -> AsyncIterator[HistoryContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Product.__table__.create)
        await conn.run_sync(Persona.__table__.create)
        await conn.run_sync(Evaluation.__table__.create)
        await conn.run_sync(Survey.__table__.create)
        await conn.run_sync(Answer.__table__.create)
        await conn.run_sync(Report.__table__.create)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield HistoryContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(ctx: HistoryContext, code: str) -> str:
    r = await ctx.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert r.status_code == 200
    return str(r.json()["token"])


async def _seed_evaluation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int,
    status: str = "done",
    with_survey: bool = True,
    with_report: bool = True,
    persona_answers: int = 3,
) -> Evaluation:
    """Insert a minimal evaluation + optional survey/report/answers into the test DB."""
    async with session_factory() as session:
        product = Product(
            user_id=user_id,
            name="珀莱雅红宝石面霜",
            description="六胜肽+A醇",
            category="面霜",
            brand="珀莱雅",
            image_urls=["https://cdn.test/img.jpg"],
            status="ready",
        )
        session.add(product)
        await session.flush()

        evaluation = Evaluation(
            user_id=user_id,
            product_id=product.id,
            status=status,
            progress=100 if status == "done" else 0,
            selected_persona_ids=[],
            credit_cost=0,
        )
        session.add(evaluation)
        await session.flush()

        survey = None
        if with_survey:
            survey = Survey(
                evaluation_id=evaluation.id,
                product_id=product.id,
                questions=[{"id": f"q{i:02d}", "type": "scale_1_5"} for i in range(30)],
                version=2,
                generated_by="ai",
            )
            session.add(survey)
            await session.flush()
            evaluation.survey_id = survey.id

        if with_report:
            report = Report(
                evaluation_id=evaluation.id,
                summary="整体评价偏正面，复购意愿较高，价格敏感度中等。",
                metrics={},
            )
            session.add(report)

        # Add persona answers — each answer needs a distinct persona (unique constraint)
        for i in range(persona_answers):
            persona = Persona(
                name=f"测试角色{i}",
                age=28,
                city="上海",
                gender="female",
                profile={},          # NOT NULL in schema
                ocean_o=70, ocean_c=60, ocean_e=50, ocean_a=65, ocean_n=40,
            )
            session.add(persona)
            await session.flush()

            answer = Answer(
                evaluation_id=evaluation.id,
                survey_id=survey.id if survey else None,
                persona_id=persona.id,
                answers=[],
                overall_intent=4,
                sentiment="positive",
                status="done",
            )
            session.add(answer)

        await session.commit()
        return evaluation


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

async def test_history_requires_auth(ctx: HistoryContext) -> None:
    r = await ctx.client.get("/api/v1/history")
    assert r.status_code == 401


async def test_history_empty_for_new_user(ctx: HistoryContext) -> None:
    token = await _login(ctx, "hist_empty")
    r = await ctx.client.get(
        "/api/v1/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_history_returns_evaluation_with_survey_and_report(ctx: HistoryContext) -> None:
    token = await _login(ctx, "hist_full")

    # Get the user_id from /me
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    await _seed_evaluation(
        ctx.session_factory,
        user_id=user_id,
        status="done",
        with_survey=True,
        with_report=True,
        persona_answers=5,
    )

    r = await ctx.client.get(
        "/api/v1/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1

    item = items[0]
    assert item["status"] == "done"
    assert item["progress"] == 100
    assert item["product"]["name"] == "珀莱雅红宝石面霜"
    assert item["product"]["brand"] == "珀莱雅"
    assert item["product"]["image_url"] == "https://cdn.test/img.jpg"
    assert item["survey"]["question_count"] == 30
    assert item["survey"]["version"] == 2
    assert "整体评价" in item["report"]["summary"]


async def test_history_evaluation_without_report(ctx: HistoryContext) -> None:
    """An evaluation that hasn't generated a report yet should have report=null."""
    token = await _login(ctx, "hist_no_report")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    await _seed_evaluation(
        ctx.session_factory,
        user_id=user_id,
        status="running",
        with_survey=True,
        with_report=False,
        persona_answers=0,
    )

    r = await ctx.client.get(
        "/api/v1/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["status"] == "running"
    assert item["survey"] is not None
    assert item["report"] is None


async def test_history_evaluation_without_survey(ctx: HistoryContext) -> None:
    """An evaluation with no survey should have survey=null."""
    token = await _login(ctx, "hist_no_survey")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    await _seed_evaluation(
        ctx.session_factory,
        user_id=user_id,
        status="pending",
        with_survey=False,
        with_report=False,
        persona_answers=0,
    )

    r = await ctx.client.get(
        "/api/v1/history", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["survey"] is None
    assert item["report"] is None


async def test_history_sorted_newest_first(ctx: HistoryContext) -> None:
    """Multiple evaluations should come back newest-first."""
    token = await _login(ctx, "hist_order")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    # Create 3 evaluations — IDs are auto-increment so newer = higher ID
    for _ in range(3):
        await _seed_evaluation(ctx.session_factory, user_id=user_id, persona_answers=0)

    r = await ctx.client.get(
        "/api/v1/history", headers={"Authorization": f"Bearer {token}"}
    )
    items = r.json()["items"]
    assert len(items) == 3
    ids = [int(i["evaluation_id"]) for i in items]
    assert ids == sorted(ids, reverse=True)


async def test_history_pagination(ctx: HistoryContext) -> None:
    """Cursor pagination should work across multiple pages."""
    token = await _login(ctx, "hist_pages")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    for _ in range(5):
        await _seed_evaluation(ctx.session_factory, user_id=user_id, persona_answers=0)

    # Page 1: limit=2
    r1 = await ctx.client.get(
        "/api/v1/history?limit=2", headers={"Authorization": f"Bearer {token}"}
    )
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["has_more"] is True
    cursor = body1["next_cursor"]
    assert cursor is not None

    # Page 2 via cursor
    r2 = await ctx.client.get(
        f"/api/v1/history?limit=2&cursor={cursor}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body2 = r2.json()
    assert len(body2["items"]) == 2
    assert body2["has_more"] is True

    # Page 3 — last page
    r3 = await ctx.client.get(
        f"/api/v1/history?limit=2&cursor={body2['next_cursor']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body3 = r3.json()
    assert len(body3["items"]) == 1
    assert body3["has_more"] is False


async def test_history_isolation_between_users(ctx: HistoryContext) -> None:
    """User A should not see User B's evaluations."""
    token_a = await _login(ctx, "hist_user_a")
    token_b = await _login(ctx, "hist_user_b")

    me_b = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"}
    )
    user_b_id = int(me_b.json()["id"])

    # Only user B has evaluations
    await _seed_evaluation(ctx.session_factory, user_id=user_b_id, persona_answers=0)

    r = await ctx.client.get(
        "/api/v1/history", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert r.json()["items"] == []


async def test_history_endpoint_in_openapi(ctx: HistoryContext) -> None:
    r = await ctx.client.get("/openapi.json")
    assert "/api/v1/history" in r.text
