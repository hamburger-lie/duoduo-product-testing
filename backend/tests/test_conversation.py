from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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


@dataclass
class ConvContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def conv_context() -> AsyncIterator[ConvContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)
        await connection.run_sync(Persona.__table__.create)
        await connection.run_sync(Evaluation.__table__.create)
        await connection.run_sync(Survey.__table__.create)
        await connection.run_sync(Answer.__table__.create)
        await connection.run_sync(Report.__table__.create)
        await connection.run_sync(Conversation.__table__.create)
        await connection.run_sync(ConversationMessage.__table__.create)
        await connection.run_sync(CreditTransaction.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield ConvContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    await engine.dispose()


async def login(ctx: ConvContext, code: str) -> str:
    """Login and return token."""

    response = await ctx.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return str(response.json()["token"])


async def create_product(ctx: ConvContext, token: str, name: str) -> str:
    """Create a product and return its ID."""

    response = await ctx.client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": "添加烟酰胺和神经酰胺，主打温和修护和提亮，适合日常护肤使用。",
            "image_object_keys": ["products/2026/05/123_front.jpg"],
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def create_system_persona(
    ctx: ConvContext,
    *,
    name: str = "林雪",
    is_critical: bool = False,
) -> str:
    """Create a system persona directly in DB."""

    async with ctx.session_factory() as session:
        persona = Persona(
            owner_id=None,
            name=name,
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
            is_critical=is_critical,
            version=1,
            status="active",
        )
        session.add(persona)
        await session.commit()
        return str(persona.id)


async def prepare_done_evaluation(
    ctx: ConvContext,
    token: str,
) -> tuple[str, str, str]:
    """Create done evaluation with 1 persona answer. Return (eval_id, persona_id, product_id)."""

    product_id = await create_product(ctx, token, "对话测试产品")
    eval_resp = await ctx.client.post(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id},
    )
    assert eval_resp.status_code == 200
    evaluation_id = str(eval_resp.json()["id"])

    await ctx.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )

    persona_id = await create_system_persona(ctx)
    await ctx.client.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": [persona_id]},
    )
    run_resp = await ctx.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_resp.status_code == 202
    assert run_resp.json()["status"] == "done"
    return evaluation_id, persona_id, product_id


async def create_conversation(
    ctx: ConvContext,
    token: str,
    evaluation_id: str,
    persona_id: str,
) -> dict[str, object]:
    """Create a conversation and return response body."""

    response = await ctx.client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"evaluation_id": evaluation_id, "persona_id": persona_id},
    )
    assert response.status_code == 200
    return response.json()


async def test_create_conversation_success(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_create")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)

    body = await create_conversation(conv_context, token, eval_id, persona_id)

    assert str(body["id"]).isdigit()
    assert body["evaluation_id"] == eval_id
    assert body["persona_id"] == persona_id
    assert body["persona_name"] == "林雪"
    assert body["message_count"] == 0
    assert body["last_message_at"] is None
    assert "深度访谈" in str(body["title"])


async def test_create_conversation_idempotent(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_idempotent")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)

    first = await create_conversation(conv_context, token, eval_id, persona_id)
    second = await create_conversation(conv_context, token, eval_id, persona_id)

    assert first["id"] == second["id"]
    async with conv_context.session_factory() as session:
        count = len((await session.scalars(select(Conversation))).all())
    assert count == 1


async def test_create_conversation_other_user_evaluation_fails(
    conv_context: ConvContext,
) -> None:
    owner_token = await login(conv_context, "conv_owner")
    other_token = await login(conv_context, "conv_other")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, owner_token)

    response = await conv_context.client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"evaluation_id": eval_id, "persona_id": persona_id},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EVALUATION_NOT_FOUND"


async def test_create_conversation_inaccessible_persona_fails(
    conv_context: ConvContext,
) -> None:
    token = await login(conv_context, "conv_bad_persona")
    eval_id, _, _ = await prepare_done_evaluation(conv_context, token)

    response = await conv_context.client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"evaluation_id": eval_id, "persona_id": "999999"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PERSONA_NOT_FOUND"


async def test_create_conversation_no_answer_fails(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_no_answer")
    eval_id, _, _ = await prepare_done_evaluation(conv_context, token)
    new_persona_id = await create_system_persona(conv_context, name="无答题角色")

    response = await conv_context.client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"evaluation_id": eval_id, "persona_id": new_persona_id},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EVALUATION_NOT_READY"


async def test_get_empty_messages(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_empty_msgs")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.get(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["has_more"] is False


async def test_send_message_returns_event_stream(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_stream")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "你好"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


async def test_send_message_contains_delta_meta_done(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_sse_events")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "你怎么看这个产品？"},
    )

    text = response.text
    assert '"event":"delta"' in text or '"event": "delta"' in text
    assert '"event":"meta"' in text or '"event": "meta"' in text
    assert '"event":"done"' in text or '"event": "done"' in text


async def test_send_message_persists_both_messages(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_persist")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "说说你的看法"},
    )

    async with conv_context.session_factory() as session:
        messages = (
            await session.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == int(str(conv["id"]))
                )
            )
        ).all()
    assert len(messages) == 2
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles


async def test_send_message_updates_message_count(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_count")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "测试"},
    )

    response = await conv_context.client.get(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


async def test_messages_order_ascending(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_order")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "第一条"},
    )

    response = await conv_context.client.get(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    items = response.json()["items"]
    assert items[0]["role"] == "user"
    assert items[1]["role"] == "assistant"
    assert items[0]["created_at"] <= items[1]["created_at"]


async def test_message_too_long_fails(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_too_long")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "x" * 501},
    )

    assert response.status_code == 400


async def test_conversation_limit_reached(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_limit")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    async with conv_context.session_factory() as session:
        entity = await session.get(Conversation, int(str(conv["id"])))
        assert entity is not None
        entity.message_count = 40
        await session.commit()

    response = await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": "超限"},
    )

    assert response.status_code == 429
    assert response.json()["code"] == "CONVERSATION_LIMIT_REACHED"


async def test_cross_user_read_fails(conv_context: ConvContext) -> None:
    owner_token = await login(conv_context, "conv_read_owner")
    other_token = await login(conv_context, "conv_read_other")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, owner_token)
    conv = await create_conversation(conv_context, owner_token, eval_id, persona_id)

    response = await conv_context.client.get(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "CONVERSATION_NOT_FOUND"


async def test_cross_user_send_fails(conv_context: ConvContext) -> None:
    owner_token = await login(conv_context, "conv_send_owner")
    other_token = await login(conv_context, "conv_send_other")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, owner_token)
    conv = await create_conversation(conv_context, owner_token, eval_id, persona_id)

    response = await conv_context.client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"content": "偷看"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "CONVERSATION_NOT_FOUND"


async def test_list_conversations_success(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_list")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


async def test_list_conversations_evaluation_filter(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_filter")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.get(
        f"/api/v1/conversations?evaluation_id={eval_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1

    response_empty = await conv_context.client.get(
        "/api/v1/conversations?evaluation_id=999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_empty.status_code == 200
    assert len(response_empty.json()["items"]) == 0


async def test_delete_conversation_success(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_delete")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    response = await conv_context.client.delete(
        f"/api/v1/conversations/{conv['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204


async def test_deleted_conversation_not_in_list(conv_context: ConvContext) -> None:
    token = await login(conv_context, "conv_delete_list")
    eval_id, persona_id, _ = await prepare_done_evaluation(conv_context, token)
    conv = await create_conversation(conv_context, token, eval_id, persona_id)

    await conv_context.client.delete(
        f"/api/v1/conversations/{conv['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await conv_context.client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 0


async def test_no_token_fails(conv_context: ConvContext) -> None:
    response = await conv_context.client.post(
        "/api/v1/conversations",
        json={"evaluation_id": "1", "persona_id": "1"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_conversation_paths_in_openapi(conv_context: ConvContext) -> None:
    response = await conv_context.client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/conversations" in paths
    assert "/api/v1/conversations/{conversation_id}/messages" in paths
    assert "/api/v1/conversations/{conversation_id}" in paths
