from __future__ import annotations

import hashlib
import hmac
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.product import Product
from app.db.models.user import User
from app.db.models.webhook_event import WebhookEvent
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.webhook_event import WebhookEventRepository


def sign_webhook_body(*, secret: str, body: bytes) -> str:
    """Return the HMAC-SHA256 signature for a webhook body."""

    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class FollowupWebhookService:
    """Create outbound follow-up webhook events from evaluation results."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.evaluations = EvaluationRepository(session)
        self.events = WebhookEventRepository(session)

    async def create_event_for_evaluation(
        self,
        *,
        evaluation_id: int,
    ) -> WebhookEvent | None:
        """Create or return a durable event for a terminal evaluation."""

        settings = get_settings()
        target_url = settings.followup_webhook_url.strip()
        if not target_url:
            return None

        evaluation = await self.evaluations.get_by_id(evaluation_id)
        if evaluation is None or evaluation.status not in {"done", "failed"}:
            return None

        event_type = f"evaluation.{evaluation.status}"
        event_id = f"{event_type}:{evaluation.id}"
        existing = await self.events.get_by_event_id(event_id=event_id)
        if existing is not None:
            return existing

        answers = await self._list_answers(evaluation_id=evaluation.id)
        user = await self.session.get(User, evaluation.user_id)
        product = await self.session.get(Product, evaluation.product_id)
        payload = self.build_payload(
            evaluation=evaluation,
            event_id=event_id,
            event_type=event_type,
            answers=answers,
            user=user,
            product=product,
        )
        return await self.events.create(
            {
                "event_id": event_id,
                "event_type": event_type,
                "target_url": target_url,
                "payload": payload,
                "status": "pending",
                "attempt_count": 0,
            }
        )

    def build_payload(
        self,
        *,
        evaluation: Evaluation,
        event_id: str,
        event_type: str,
        answers: list[Answer],
        user: User | None,
        product: Product | None,
    ) -> dict[str, object]:
        """Build the follow-up payload for the configured external receiver."""

        completed = [answer for answer in answers if answer.status == "done"]
        failed = [answer for answer in answers if answer.status == "failed"]
        intents = [
            int(answer.overall_intent)
            for answer in completed
            if answer.overall_intent is not None
        ]
        sentiment_counts = Counter(answer.sentiment for answer in completed if answer.sentiment)
        overall_sentiment = (
            sentiment_counts.most_common(1)[0][0] if sentiment_counts else "neutral"
        )
        average_intent = round(sum(intents) / len(intents), 2) if intents else None

        return {
            "event": event_type,
            "event_id": event_id,
            "occurred_at": self._format_dt(datetime.now(UTC)),
            "user_id": str(evaluation.user_id),
            "evaluation_id": str(evaluation.id),
            "product_id": str(evaluation.product_id),
            "status": evaluation.status,
            "user": {
                "id": str(evaluation.user_id),
                "openid": user.openid if user else None,
                "nickname": user.nickname if user else None,
            },
            "product": {
                "id": str(evaluation.product_id),
                "image_keys": self._image_keys(product),
            },
            "summary": {
                "total_personas": len(evaluation.selected_persona_ids),
                "completed_personas": len(completed),
                "failed_personas": len(failed),
                "average_intent": average_intent,
                "overall_sentiment": overall_sentiment,
            },
            "answers": [self._answer_payload(answer) for answer in answers],
        }

    async def _list_answers(self, *, evaluation_id: int) -> list[Answer]:
        result = await self.session.scalars(
            select(Answer).where(
                Answer.evaluation_id == evaluation_id,
                Answer.deleted_at.is_(None),
            )
        )
        return list(result.all())

    def _format_dt(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _image_keys(self, product: Product | None) -> list[str]:
        if product is None:
            return []
        return [str(value) for value in product.image_urls]

    def _answer_payload(self, answer: Answer) -> dict[str, object]:
        return {
            "persona_id": str(answer.persona_id),
            "status": answer.status,
            "answers": answer.answers,
            "overall_intent": answer.overall_intent,
            "sentiment": answer.sentiment,
            "summary_comment": answer.summary_comment,
            "thinking_process": answer.thinking_process,
            "token_input": answer.token_input,
            "token_output": answer.token_output,
            "cost_yuan": str(answer.cost_yuan) if answer.cost_yuan is not None else None,
            "error_message": answer.error_message,
        }
