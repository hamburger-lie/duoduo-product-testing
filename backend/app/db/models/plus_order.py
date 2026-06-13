from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModelMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class PlusOrder(Base, BaseModelMixin):
    """WeChat Pay orders for Plus membership."""

    __tablename__ = "plus_orders"
    __table_args__ = (
        Index("ix_plus_orders_user_created_at_desc", "user_id", desc("created_at")),
        Index("ix_plus_orders_out_trade_no", "out_trade_no", unique=True),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_fen: Mapped[int] = mapped_column(Integer, nullable=False)   # e.g. 19900 = ¥199.00
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending | paid | failed
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="plus_orders")
