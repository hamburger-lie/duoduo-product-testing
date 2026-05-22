from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.webhook_event import WebhookEvent
from app.db.repositories.base import BaseRepository


class WebhookEventRepository(BaseRepository[WebhookEvent]):
    """Repository for outbound webhook events."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=WebhookEvent)

    async def get_by_event_id(self, *, event_id: str) -> WebhookEvent | None:
        """Return one webhook event by idempotency event ID."""

        return cast(
            WebhookEvent | None,
            await self.session.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.event_id == event_id,
                    WebhookEvent.deleted_at.is_(None),
                )
            ),
        )

    async def list_ready_for_delivery(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> list[WebhookEvent]:
        """Return pending/failed events whose retry time has arrived."""

        result = await self.session.scalars(
            select(WebhookEvent)
            .where(
                WebhookEvent.deleted_at.is_(None),
                WebhookEvent.status.in_(("pending", "failed")),
                (
                    (WebhookEvent.next_attempt_at.is_(None))
                    | (WebhookEvent.next_attempt_at <= now)
                ),
            )
            .order_by(WebhookEvent.created_at.asc(), WebhookEvent.id.asc())
            .limit(limit)
        )
        return list(result.all())
