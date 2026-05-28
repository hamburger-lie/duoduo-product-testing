from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import JSONB_TYPE, Base, BaseModelMixin

if TYPE_CHECKING:
    from app.db.models.user import User


class CreditTransaction(Base, BaseModelMixin):
    """Credit ledger entries for a user."""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        Index("ix_credit_transactions_user_created_at_desc", "user_id", desc("created_at")),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="credit_transactions")


class CreditRechargeOrder(Base, BaseModelMixin):
    """Durable credit recharge order awaiting provider settlement."""

    __tablename__ = "credit_recharge_orders"
    __table_args__ = (
        Index(
            "ix_credit_recharge_orders_user_created_at_desc",
            "user_id",
            desc("created_at"),
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_credit_recharge_orders_user_idempotency_key",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_yuan: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_callback: Mapped[dict[str, object] | None] = mapped_column(JSONB_TYPE, nullable=True)

    user: Mapped["User"] = relationship(back_populates="credit_recharge_orders")
