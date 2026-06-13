from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModelMixin, JSONB_TYPE, JsonDict


class UserActivityEvent(Base, BaseModelMixin):
    """Audit-friendly record of key user actions in the mini-program."""

    __tablename__ = "user_activity_events"
    __table_args__ = (
        Index("ix_user_activity_events_user_created_at", "user_id", "created_at"),
        Index("ix_user_activity_events_event_type", "event_type"),
        Index("ix_user_activity_events_request_id", "request_id"),
    )

    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    method: Mapped[str | None] = mapped_column(String(8), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_metadata: Mapped[JsonDict | None] = mapped_column(
        "metadata",
        JSONB_TYPE,
        nullable=True,
    )
