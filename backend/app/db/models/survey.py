from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonList

if TYPE_CHECKING:
    from app.db.models.answer import Answer
    from app.db.models.evaluation import Evaluation
    from app.db.models.product import Product


class Survey(Base, BaseModelMixin):
    """Generated survey bound to an evaluation and product.

    Each evaluation may only have one survey (enforced at application layer via
    ``evaluation.survey_id`` and at DB layer via the unique constraint below).
    The ``version`` column tracks edit history on the *same* row.
    """

    __tablename__ = "surveys"
    __table_args__ = (
        UniqueConstraint("evaluation_id", name="uq_surveys_evaluation_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    questions: Mapped[JsonList] = mapped_column(JSONB_TYPE, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_by: Mapped[str] = mapped_column(String(16), nullable=False, default="ai")

    evaluation: Mapped["Evaluation"] = relationship(
        back_populates="generated_surveys",
        foreign_keys=[evaluation_id],
    )
    linked_evaluation: Mapped["Evaluation | None"] = relationship(
        back_populates="survey",
        foreign_keys="Evaluation.survey_id",
        uselist=False,
    )
    product: Mapped["Product"] = relationship(back_populates="surveys")
    answers: Mapped[list["Answer"]] = relationship(back_populates="survey")
