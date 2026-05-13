from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonList

if TYPE_CHECKING:
    from app.db.models.evaluation import Evaluation
    from app.db.models.persona import Persona
    from app.db.models.survey import Survey


class Answer(Base, BaseModelMixin):
    """Persona answers for a survey within one evaluation."""

    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "persona_id", name="uq_answers_evaluation_persona"),
        Index("ix_answers_persona_created_at_desc", "persona_id", desc("created_at")),
    )

    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id"), nullable=False)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    answers: Mapped[JsonList] = mapped_column(JSONB_TYPE, nullable=False)
    overall_intent: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_yuan: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="answers")
    survey: Mapped["Survey"] = relationship(back_populates="answers")
    persona: Mapped["Persona"] = relationship(back_populates="answers")
