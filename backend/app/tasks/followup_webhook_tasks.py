from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings
from app.services.followup_webhook_service import sign_webhook_body
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro: object) -> dict[str, object]:
    loop = asyncio.new_event_loop()
    try:
        result: dict[str, object] = loop.run_until_complete(coro)  # type: ignore[arg-type]
        return result
    finally:
        loop.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="followup_webhook.deliver",
    bind=True,
    max_retries=0,
)
def deliver_followup_webhook_event_task(self: object, event_id: int) -> dict[str, object]:
    """Celery wrapper for delivering one follow-up webhook event."""

    return _run_async(deliver_followup_webhook_event(event_id))


async def deliver_followup_webhook_event(event_id: int) -> dict[str, object]:
    """Deliver one webhook event and persist delivery status."""

    from app.db.models.webhook_event import WebhookEvent
    from app.db.session import AsyncSessionFactory

    settings = get_settings()
    async with AsyncSessionFactory() as session:
        event = await session.get(WebhookEvent, event_id)
        if event is None:
            return {"status": "missing", "event_id": str(event_id)}
        if event.status == "delivered":
            return {"status": "delivered", "event_id": str(event_id)}

        body = json.dumps(
            event.payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event-Id": event.event_id,
            "X-Webhook-Signature": sign_webhook_body(
                secret=settings.followup_webhook_secret,
                body=body,
            ),
        }

        event.attempt_count += 1
        try:
            timeout = httpx.Timeout(settings.followup_webhook_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    event.target_url,
                    content=body,
                    headers=headers,
                )
            if 200 <= response.status_code < 300:
                event.status = "delivered"
                event.delivered_at = datetime.now(UTC)
                event.last_error = None
                event.next_attempt_at = None
                await session.commit()
                return {"status": "delivered", "event_id": str(event.id)}

            event.status = "failed"
            event.last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            event.next_attempt_at = _next_attempt_at(event.attempt_count)
            await session.commit()
            return {"status": "failed", "event_id": str(event.id)}
        except httpx.HTTPError as exc:
            event.status = "failed"
            event.last_error = str(exc)[:200]
            event.next_attempt_at = _next_attempt_at(event.attempt_count)
            await session.commit()
            logger.warning(
                "followup_webhook_delivery_failed",
                extra={
                    "event": "followup_webhook_delivery_failed",
                    "webhook_event_id": event.id,
                    "attempt_count": event.attempt_count,
                },
            )
            return {"status": "failed", "event_id": str(event.id)}


def _next_attempt_at(attempt_count: int) -> datetime:
    delay_seconds = min(3600, 2 ** max(0, attempt_count - 1) * 60)
    return datetime.now(UTC) + timedelta(seconds=delay_seconds)
