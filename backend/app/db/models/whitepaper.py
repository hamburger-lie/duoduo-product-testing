from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModelMixin


class Whitepaper(Base, BaseModelMixin):
    """Generated CIBE-style whitepaper for an evaluation."""

    __tablename__ = "whitepapers"
    __table_args__ = (
        UniqueConstraint("evaluation_id", name="uq_whitepapers_evaluation_id"),
    )

    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
