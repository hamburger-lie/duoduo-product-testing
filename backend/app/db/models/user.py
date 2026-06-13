from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseModelMixin

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.credit import CreditTransaction
    from app.db.models.evaluation import Evaluation
    from app.db.models.persona import Persona
    from app.db.models.plus_order import PlusOrder
    from app.db.models.product import Product


class User(Base, BaseModelMixin):
    """Application user."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_openid", "openid"),
        Index("ix_users_unionid", "unionid"),
        Index("ix_users_phone_number", "phone_number"),
    )

    openid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    unionid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    is_plus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    plus_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    products: Mapped[list["Product"]] = relationship(back_populates="user")
    personas: Mapped[list["Persona"]] = relationship(back_populates="owner")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="user")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(back_populates="user")
    plus_orders: Mapped[list["PlusOrder"]] = relationship(back_populates="user")
