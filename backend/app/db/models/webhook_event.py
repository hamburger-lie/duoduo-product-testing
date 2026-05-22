from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonDict


class WebhookEvent(Base, BaseModelMixin):
    """Durable outbound webhook event."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        Index("ix_webhook_events_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_webhook_events_event_id", "event_id", unique=True),
    )

    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    payload: Mapped[JsonDict] = mapped_column(JSONB_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
