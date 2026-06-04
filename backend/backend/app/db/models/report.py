from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonDict, JsonList

if TYPE_CHECKING:
    from app.db.models.evaluation import Evaluation


class Report(Base, BaseModelMixin):
    """Generated report for an evaluation."""

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("evaluation_id", name="uq_reports_evaluation_id"),
        UniqueConstraint("share_token", name="uq_reports_share_token"),
    )

    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[JsonDict | None] = mapped_column(JSONB_TYPE, nullable=True)
    top_pros: Mapped[JsonList | None] = mapped_column(JSONB_TYPE, nullable=True)
    top_cons: Mapped[JsonList | None] = mapped_column(JSONB_TYPE, nullable=True)
    persona_segments: Mapped[JsonDict | None] = mapped_column(JSONB_TYPE, nullable=True)
    dimension_analysis: Mapped[JsonList | None] = mapped_column(JSONB_TYPE, nullable=True)
    dimension_analysis_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    share_token: Mapped[str | None] = mapped_column(String(32), nullable=True)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="report")

