"""E2E test: complete mock flow from login to conversation.

Covers the full happy path using real API routes with in-memory SQLite.
No real ARK key required — everything uses mock/default providers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.conversation import Conversation, ConversationMessage
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app


@dataclass
class E2EContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def ctx() -> AsyncIterator[E2EContext]:
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
        await conn.run_sync(Conversation.__table__.create)
        await conn.run_sync(ConversationMessage.__table__.create)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield E2EContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_mock_flow(ctx: E2EContext) -> None:
    """Run the entire MVP flow end-to-end using mock providers."""

    c = ctx.client

    # ── 1. Login ──
    resp = await c.post("/api/v1/auth/wechat/login", json={"code": "e2e_test_user"})
    assert resp.status_code == 200
    login_data = resp.json()
    assert "token" in login_data
    token = login_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # ── 2. Update profile ──
    resp = await c.patch(
        "/api/v1/auth/profile",
        headers=headers,
        json={"role_type": "manufacturer", "nickname": "E2E品牌方"},
    )
    assert resp.status_code == 200
    assert resp.json()["role_type"] == "manufacturer"

    # ── 3. Upload URL ──
    resp = await c.post(
        "/api/v1/products/upload-url",
        headers=headers,
        json={"filename": "front.jpg", "mime_type": "image/jpeg", "size_bytes": 1024},
    )
    assert resp.status_code == 200
    upload_data = resp.json()
    assert "upload_url" in upload_data
    assert "object_key" in upload_data
    object_key = upload_data["object_key"]

    # ── 4. Create product ──
    resp = await c.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "E2E测试面霜",
            "description": "温和保湿面霜，添加烟酰胺和神经酰胺。",
            "image_object_keys": [object_key],
        },
    )
    assert resp.status_code == 200
    product = resp.json()
    product_id = product["id"]
    assert product["status"] == "ready"

    # ── 5. Create evaluation ──
    resp = await c.post(
        "/api/v1/evaluations",
        headers=headers,
        json={"product_id": product_id},
    )
    assert resp.status_code == 200
    evaluation = resp.json()
    evaluation_id = evaluation["id"]
    assert evaluation["status"] == "pending"

    # ── 6. Generate survey ──
    resp = await c.post(
        "/api/v1/surveys/generate",
        headers=headers,
        json={
            "product_id": product_id,
            "evaluation_id": evaluation_id,
        },
    )
    assert resp.status_code == 200
    survey = resp.json()
    survey_id = survey["id"]
    assert len(survey["questions"]) > 0

    # Verify evaluation now has survey_id
    resp = await c.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["survey_id"] == survey_id

    # ── 7. Recommend personas ──
    resp = await c.get(
        f"/api/v1/personas/recommend?product_id={product_id}&count=20",
        headers=headers,
    )
    assert resp.status_code == 200
    recommend_data = resp.json()

    # Seed personas if recommendation returns empty (no seeded data)
    if len(recommend_data.get("items", [])) == 0:
        persona = Persona(
            owner_id=None,
            name="E2E测试角色",
            avatar="person",
            age=28,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="产品经理",
            income_monthly=25000,
            ocean_o=70,
            ocean_c=80,
            ocean_e=50,
            ocean_a=60,
            ocean_n=55,
            persona_tag="成分党",
            profile={"bio": "关注成分"},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        async with ctx.session_factory() as session:
            session.add(persona)
            await session.commit()
            persona_id = str(persona.id)

        resp = await c.get(
            f"/api/v1/personas/recommend?product_id={product_id}&count=20",
            headers=headers,
        )
        assert resp.status_code == 200
        recommend_data = resp.json()

    assert len(recommend_data["items"]) >= 1
    persona_id = str(recommend_data["items"][0]["id"])

    # ── 8. Select personas ──
    resp = await c.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers=headers,
        json={"persona_ids": [persona_id]},
    )
    assert resp.status_code == 200

    # ── 9. Run evaluation ──
    resp = await c.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers=headers,
    )
    assert resp.status_code == 202
    run_data = resp.json()
    assert run_data["status"] == "done"
    assert run_data["progress"] == 100

    # ── 10. Get evaluation (verify done) ──
    resp = await c.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"

    # ── 11. Get answers ──
    resp = await c.get(
        f"/api/v1/evaluations/{evaluation_id}/answers",
        headers=headers,
    )
    assert resp.status_code == 200
    answers_data = resp.json()
    assert isinstance(answers_data, list)
    assert len(answers_data) >= 1

    # ── 12. Get report ──
    resp = await c.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    report = resp.json()
    assert "summary" in report
    assert "metrics" in report
    assert "top_pros" in report
    assert "top_cons" in report
    assert "ai_disclaimer" in report

    # ── 13. Create conversation ──
    resp = await c.post(
        "/api/v1/conversations",
        headers=headers,
        json={"evaluation_id": evaluation_id, "persona_id": persona_id},
    )
    assert resp.status_code == 200
    conversation = resp.json()
    conversation_id = conversation["id"]
    assert str(conversation["evaluation_id"]) == str(evaluation_id)
    assert str(conversation["persona_id"]) == str(persona_id)

    # ── 14. Send message (SSE stream) ──
    resp = await c.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "你好，请问你对这款面霜怎么看？"},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    sse_text = resp.text
    assert '"event": "delta"' in sse_text or '"event":"delta"' in sse_text
    assert '"event": "meta"' in sse_text or '"event":"meta"' in sse_text
    assert '"event": "done"' in sse_text or '"event":"done"' in sse_text

    # ── 15. Get messages ──
    resp = await c.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert resp.status_code == 200
    messages = resp.json()
    roles = [m["role"] for m in messages["items"]]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_report_contains_required_fields(ctx: E2EContext) -> None:
    """Report response includes summary, metrics, top_pros, top_cons, ai_disclaimer."""

    c = ctx.client

    resp = await c.post("/api/v1/auth/wechat/login", json={"code": "e2e_report"})
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "报告测试面霜",
            "description": "测试报告生成，添加烟酰胺和神经酰胺。",
            "image_object_keys": ["products/2026/05/report_test.jpg"],
        },
    )
    assert resp.status_code == 200
    product_id = resp.json()["id"]

    resp = await c.post("/api/v1/evaluations", headers=headers, json={"product_id": product_id})
    evaluation_id = resp.json()["id"]

    await c.post(
        "/api/v1/surveys/generate",
        headers=headers,
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )

    persona = Persona(
        owner_id=None,
        name="报告测试角色",
        avatar="person",
        age=30,
        gender="female",
        city="北京",
        city_tier=1,
        occupation="设计师",
        income_monthly=20000,
        ocean_o=70, ocean_c=70, ocean_e=70, ocean_a=70, ocean_n=50,
        persona_tag="品质党",
        profile={"bio": "注重品质"},
        categories=["美妆"],
        is_critical=False,
        version=1,
        status="active",
    )
    async with ctx.session_factory() as session:
        session.add(persona)
        await session.commit()
        p_id = str(persona.id)

    await c.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers=headers,
        json={"persona_ids": [p_id]},
    )
    await c.post(f"/api/v1/evaluations/{evaluation_id}/run", headers=headers)

    resp = await c.get(f"/api/v1/reports/by-evaluation/{evaluation_id}", headers=headers)
    assert resp.status_code == 200
    report = resp.json()
    assert len(report["summary"]) > 0
    assert "overall_intent" in report["metrics"]
    assert "dimensions_radar" in report["metrics"]
    assert isinstance(report["top_pros"], list)
    assert isinstance(report["top_cons"], list)
    assert len(report["ai_disclaimer"]) > 0


@pytest.mark.asyncio
async def test_conversation_sse_events(ctx: E2EContext) -> None:
    """SSE stream contains delta, meta (with message_id), and done events."""

    c = ctx.client

    resp = await c.post("/api/v1/auth/wechat/login", json={"code": "e2e_sse"})
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await c.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "SSE测试面霜",
            "description": "测试SSE流式，添加烟酰胺成分。",
            "image_object_keys": ["products/2026/05/sse_test.jpg"],
        },
    )
    product_id = resp.json()["id"]

    resp = await c.post("/api/v1/evaluations", headers=headers, json={"product_id": product_id})
    evaluation_id = resp.json()["id"]

    await c.post(
        "/api/v1/surveys/generate",
        headers=headers,
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )

    persona = Persona(
        owner_id=None,
        name="SSE角色",
        avatar="person",
        age=25,
        gender="male",
        city="深圳",
        city_tier=1,
        occupation="程序员",
        income_monthly=30000,
        ocean_o=60, ocean_c=70, ocean_e=50, ocean_a=60, ocean_n=40,
        persona_tag="科技控",
        profile={},
        categories=["美妆"],
        is_critical=False,
        version=1,
        status="active",
    )
    async with ctx.session_factory() as session:
        session.add(persona)
        await session.commit()
        p_id = str(persona.id)

    await c.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers=headers,
        json={"persona_ids": [p_id]},
    )
    await c.post(f"/api/v1/evaluations/{evaluation_id}/run", headers=headers)

    resp = await c.post(
        "/api/v1/conversations",
        headers=headers,
        json={"evaluation_id": evaluation_id, "persona_id": p_id},
    )
    conversation_id = resp.json()["id"]

    resp = await c.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "你好"},
    )

    import json

    sse_text = resp.text
    lines = [ln for ln in sse_text.strip().split("\n\n") if ln.startswith("data: ")]
    events = [json.loads(ln[6:]) for ln in lines]

    event_types = [e["event"] for e in events]
    assert "delta" in event_types
    assert "meta" in event_types
    assert "done" in event_types

    meta_event = next(e for e in events if e["event"] == "meta")
    assert "message_id" in meta_event
    assert "tokens" in meta_event
