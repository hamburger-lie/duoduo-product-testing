from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin, JsonDict, JsonList

if TYPE_CHECKING:
    from app.db.models.evaluation import Evaluation
    from app.db.models.survey import Survey
    from app.db.models.user import User


class Product(Base, BaseModelMixin):
    """Product submitted for evaluation."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_user_created_at_desc", "user_id", desc("created_at")),
        Index("ix_products_category", "category"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sub_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_range: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_urls: Mapped[JsonList] = mapped_column(JSONB_TYPE, nullable=False, default=list)
    ai_summary: Mapped[JsonDict | None] = mapped_column(JSONB_TYPE, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")

    user: Mapped["User"] = relationship(back_populates="products")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="product")
    surveys: Mapped[list["Survey"]] = relationship(back_populates="product")
