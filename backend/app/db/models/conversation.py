from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModelMixin

if TYPE_CHECKING:
    from app.db.models.evaluation import Evaluation
    from app.db.models.persona import Persona
    from app.db.models.user import User


class Conversation(Base, BaseModelMixin):
    """One deep-chat thread for a persona within an evaluation."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_evaluation_persona", "user_id", "evaluation_id", "persona_id"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="conversations")
    evaluation: Mapped["Evaluation"] = relationship(back_populates="conversations")
    persona: Mapped["Persona"] = relationship(back_populates="conversations")
    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation")


class ConversationMessage(Base, BaseModelMixin):
    """Stored chat message within a conversation."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("ix_conversation_messages_conversation_created_at", "conversation_id", "created_at"),
    )

    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_yuan: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
