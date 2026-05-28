from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.credit import CreditRechargeOrder, CreditTransaction
from app.db.repositories.base import BaseRepository


class CreditTransactionRepository(BaseRepository[CreditTransaction]):
    """Repository for credit transactions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=CreditTransaction)


class CreditRechargeOrderRepository(BaseRepository[CreditRechargeOrder]):
    """Repository for credit recharge orders."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=CreditRechargeOrder)
