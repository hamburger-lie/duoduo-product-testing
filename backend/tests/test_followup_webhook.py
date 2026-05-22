from __future__ import annotations

import hmac
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.product import Product
from app.db.models.user import User
from app.db.models.webhook_event import WebhookEvent
from app.services.followup_webhook_service import FollowupWebhookService, sign_webhook_body
from app.tasks.followup_webhook_tasks import deliver_followup_webhook_event


@dataclass
class WebhookContext:
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def webhook_context() -> AsyncIterator[WebhookContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)
        await connection.run_sync(Evaluation.__table__.create)
        await connection.run_sync(Answer.__table__.create)
        await connection.run_sync(WebhookEvent.__table__.create)

    yield WebhookContext(session_factory=session_factory)

    await engine.dispose()


async def create_done_evaluation(context: WebhookContext) -> int:
    async with context.session_factory() as session:
        user = User(openid="followup_user", nickname="Followup User")
        session.add(user)
        await session.flush()

        product = Product(
            user_id=user.id,
            name="回传测试产品",
            description="用于 webhook 回传测试",
            price=Decimal("88.00"),
            image_urls=["tos/products/demo-image.png"],
            ai_summary={"category": "美妆"},
            status="ready",
        )
        session.add(product)
        await session.flush()

        evaluation = Evaluation(
            user_id=user.id,
            product_id=product.id,
            survey_id=None,
            selected_persona_ids=["101", "102"],
            status="done",
            progress=100,
            credit_cost=20,
        )
        session.add(evaluation)
        await session.flush()

        session.add_all(
            [
                Answer(
                    evaluation_id=evaluation.id,
                    survey_id=1,
                    persona_id=101,
                    answers=[{"qid": "q1", "type": "scale_1_5", "answer": 5}],
                    overall_intent=5,
                    sentiment="positive",
                    summary_comment="喜欢温和成分",
                    thinking_process="判断过程 A",
                    status="done",
                    token_input=100,
                    token_output=20,
                    cost_yuan=Decimal("0.1200"),
                ),
                Answer(
                    evaluation_id=evaluation.id,
                    survey_id=1,
                    persona_id=102,
                    answers=[{"qid": "q1", "type": "scale_1_5", "answer": 3}],
                    overall_intent=3,
                    sentiment="neutral",
                    summary_comment="担心价格",
                    thinking_process="判断过程 B",
                    status="failed",
                    token_input=0,
                    token_output=0,
                    cost_yuan=Decimal("0.0000"),
                ),
            ]
        )
        await session.commit()
        return evaluation.id


def test_sign_webhook_body_uses_hmac_sha256() -> None:
    body = b'{"event":"evaluation.done"}'
    signature = sign_webhook_body(secret="secret-key", body=body)

    expected = hmac.new(b"secret-key", body, "sha256").hexdigest()
    assert signature == f"sha256={expected}"


async def test_create_event_builds_minimal_followup_payload(
    webhook_context: WebhookContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_URL", "https://crm.example.test/webhook")
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_SECRET", "secret-key")
    get_settings.cache_clear()
    evaluation_id = await create_done_evaluation(webhook_context)

    async with webhook_context.session_factory() as session:
        event = await FollowupWebhookService(session).create_event_for_evaluation(
            evaluation_id=evaluation_id,
        )
        await session.commit()

    assert event is not None
    assert event.event_type == "evaluation.done"
    assert event.target_url == "https://crm.example.test/webhook"
    assert event.payload["evaluation_id"] == str(evaluation_id)
    assert event.payload["status"] == "done"
    assert event.payload["user"] == {
        "id": event.payload["user_id"],
        "openid": "followup_user",
        "nickname": "Followup User",
    }
    assert event.payload["product"] == {
        "id": event.payload["product_id"],
        "image_keys": ["tos/products/demo-image.png"],
    }
    assert event.payload["answers"] == [
        {
            "persona_id": "101",
            "status": "done",
            "answers": [{"qid": "q1", "type": "scale_1_5", "answer": 5}],
            "overall_intent": 5,
            "sentiment": "positive",
            "summary_comment": "喜欢温和成分",
            "thinking_process": "判断过程 A",
            "token_input": 100,
            "token_output": 20,
            "cost_yuan": "0.1200",
            "error_message": None,
        },
        {
            "persona_id": "102",
            "status": "failed",
            "answers": [{"qid": "q1", "type": "scale_1_5", "answer": 3}],
            "overall_intent": 3,
            "sentiment": "neutral",
            "summary_comment": "担心价格",
            "thinking_process": "判断过程 B",
            "token_input": 0,
            "token_output": 0,
            "cost_yuan": "0.0000",
            "error_message": None,
        },
    ]
    assert event.payload["summary"] == {
        "total_personas": 2,
        "completed_personas": 1,
        "failed_personas": 1,
        "average_intent": 5.0,
        "overall_sentiment": "positive",
    }
    assert "task_id" not in event.payload


async def test_create_event_is_disabled_without_target_url(
    webhook_context: WebhookContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOLLOWUP_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()
    evaluation_id = await create_done_evaluation(webhook_context)

    async with webhook_context.session_factory() as session:
        event = await FollowupWebhookService(session).create_event_for_evaluation(
            evaluation_id=evaluation_id,
        )

    assert event is None


async def test_create_event_is_idempotent(
    webhook_context: WebhookContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_URL", "https://crm.example.test/webhook")
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_SECRET", "secret-key")
    get_settings.cache_clear()
    evaluation_id = await create_done_evaluation(webhook_context)

    async with webhook_context.session_factory() as session:
        service = FollowupWebhookService(session)
        first = await service.create_event_for_evaluation(evaluation_id=evaluation_id)
        second = await service.create_event_for_evaluation(evaluation_id=evaluation_id)
        await session.commit()

    assert first is not None
    assert second is not None
    assert first.id == second.id


async def test_delivery_marks_event_delivered_and_sends_signature_headers(
    webhook_context: WebhookContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_URL", "https://crm.example.test/webhook")
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_SECRET", "secret-key")
    get_settings.cache_clear()
    evaluation_id = await create_done_evaluation(webhook_context)

    async with webhook_context.session_factory() as session:
        event = await FollowupWebhookService(session).create_event_for_evaluation(
            evaluation_id=evaluation_id,
        )
        assert event is not None
        await session.commit()
        event_id = event.id

    sent: dict[str, Any] = {}

    class FakeResponse:
        status_code = 204
        text = ""

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(
            self,
            url: str,
            *,
            content: bytes,
            headers: dict[str, str],
        ) -> FakeResponse:
            sent["url"] = url
            sent["content"] = content
            sent["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("app.db.session.AsyncSessionFactory", webhook_context.session_factory)
    monkeypatch.setattr("app.tasks.followup_webhook_tasks.httpx.AsyncClient", FakeClient)

    result = await deliver_followup_webhook_event(event_id)

    assert result == {"status": "delivered", "event_id": str(event_id)}
    assert sent["url"] == "https://crm.example.test/webhook"
    body = sent["content"]
    assert json.loads(body)["evaluation_id"] == str(evaluation_id)
    assert sent["headers"]["X-Webhook-Event-Id"] == f"evaluation.done:{evaluation_id}"
    assert sent["headers"]["X-Webhook-Signature"] == sign_webhook_body(
        secret="secret-key",
        body=body,
    )
    async with webhook_context.session_factory() as session:
        event = await session.get(WebhookEvent, event_id)
        assert event is not None
        assert event.status == "delivered"
        assert event.attempt_count == 1
        assert event.delivered_at is not None


async def test_delivery_marks_event_failed_on_non_2xx(
    webhook_context: WebhookContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_URL", "https://crm.example.test/webhook")
    monkeypatch.setenv("FOLLOWUP_WEBHOOK_SECRET", "secret-key")
    get_settings.cache_clear()
    evaluation_id = await create_done_evaluation(webhook_context)

    async with webhook_context.session_factory() as session:
        event = await FollowupWebhookService(session).create_event_for_evaluation(
            evaluation_id=evaluation_id,
        )
        assert event is not None
        await session.commit()
        event_id = event.id

    class FakeResponse:
        status_code = 500
        text = "server exploded"

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def post(
            self,
            url: str,
            *,
            content: bytes,
            headers: dict[str, str],
        ) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.db.session.AsyncSessionFactory", webhook_context.session_factory)
    monkeypatch.setattr("app.tasks.followup_webhook_tasks.httpx.AsyncClient", FakeClient)

    result = await deliver_followup_webhook_event(event_id)

    assert result["status"] == "failed"
    async with webhook_context.session_factory() as session:
        event = await session.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id))
        assert event is not None
        assert event.status == "failed"
        assert event.attempt_count == 1
        assert "HTTP 500" in (event.last_error or "")
