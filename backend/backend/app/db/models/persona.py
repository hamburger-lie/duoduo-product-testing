from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonDict, JsonList

if TYPE_CHECKING:
    from app.db.models.answer import Answer
    from app.db.models.conversation import Conversation
    from app.db.models.user import User


class Persona(Base, BaseModelMixin):
    """System or user-defined consumer persona."""

    __tablename__ = "personas"
    __table_args__ = (
        Index("ix_personas_owner_id", "owner_id"),
        Index("ix_personas_categories_gin", "categories", postgresql_using="gin"),
        Index("ix_personas_is_critical", "is_critical"),
        Index("ix_personas_persona_tag", "persona_tag"),
    )

    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(64), nullable=True)
    age: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False)
    city: Mapped[str] = mapped_column(String(32), nullable=False)
    city_tier: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    income_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocean_o: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ocean_c: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ocean_e: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ocean_a: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ocean_n: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    persona_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile: Mapped[JsonDict] = mapped_column(JSONB_TYPE, nullable=False)
    categories: Mapped[JsonList] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    owner: Mapped["User | None"] = relationship(back_populates="personas")
    answers: Mapped[list["Answer"]] = relationship(back_populates="persona")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="persona")
