from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModelMixin


class CustomizeRequest(Base, BaseModelMixin):
    """Authenticated user's custom service request."""

    __tablename__ = "customize_requests"
    __table_args__ = (
        Index("ix_customize_requests_user_created_at", "user_id", "created_at"),
        Index("ix_customize_requests_status", "status"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
