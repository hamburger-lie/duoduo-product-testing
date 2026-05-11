from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonList

if TYPE_CHECKING:
    from app.db.models.answer import Answer
    from app.db.models.conversation import Conversation
    from app.db.models.product import Product
    from app.db.models.report import Report
    from app.db.models.survey import Survey
    from app.db.models.user import User


class Evaluation(Base, BaseModelMixin):
    """Evaluation job for a product."""

    __tablename__ = "evaluations"
    __table_args__ = (
        Index("ix_evaluations_user_created_at_desc", "user_id", desc("created_at")),
        Index("ix_evaluations_status", "status"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    survey_id: Mapped[int | None] = mapped_column(ForeignKey("surveys.id"), nullable=True)
    selected_persona_ids: Mapped[JsonList] = mapped_column(
        JSONB_TYPE,
        nullable=False,
        default=list,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="evaluations")
    product: Mapped["Product"] = relationship(back_populates="evaluations")
    survey: Mapped["Survey | None"] = relationship(
        back_populates="linked_evaluation",
        foreign_keys=[survey_id],
    )
    generated_surveys: Mapped[list["Survey"]] = relationship(
        back_populates="evaluation",
        foreign_keys="Survey.evaluation_id",
    )
    answers: Mapped[list["Answer"]] = relationship(back_populates="evaluation")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="evaluation")
    report: Mapped["Report | None"] = relationship(back_populates="evaluation", uselist=False)
