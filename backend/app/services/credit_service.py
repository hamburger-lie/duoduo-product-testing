from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.credit import CreditTransaction
from app.db.models.user import User
from app.schemas.credit import (
    CreditBalanceResponse,
    CreditTransactionItem,
    CreditTransactionListResponse,
)


class CreditService:
    """Manage user credit balance and transaction ledger.

    MVP rules:
    - credit_balance lives on the User row (denormalised for fast reads).
    - Every credit change writes a CreditTransaction row.
    - Enforcement (blocking ops when balance < 0) is NOT applied in MVP —
      see API_CONTRACT §INSUFFICIENT_CREDITS.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Write helpers
    # ------------------------------------------------------------------ #

    async def initialize(self, user: User, amount: int = 1000) -> CreditTransaction:
        """Record the welcome-credit transaction for a brand-new user.

        The User row's ``credit_balance`` is already set to 1000 at creation
        time (model default), so we only need to write the ledger entry.
        """
        tx = CreditTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=user.credit_balance,
            reason="init",
            ref_type=None,
            ref_id=None,
            note="新用户注册赠送积分",
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def deduct(
        self,
        user: User,
        amount: int,
        *,
        reason: str,
        ref_type: str | None = None,
        ref_id: int | None = None,
        note: str | None = None,
    ) -> CreditTransaction:
        """Deduct ``amount`` credits from the user.

        ``amount`` should be a *positive* integer; the ledger stores it as
        negative automatically.
        """
        user.credit_balance -= amount
        tx = CreditTransaction(
            user_id=user.id,
            amount=-amount,
            balance_after=user.credit_balance,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def refund(
        self,
        user: User,
        amount: int,
        *,
        reason: str = "refund",
        ref_type: str | None = None,
        ref_id: int | None = None,
        note: str | None = None,
    ) -> CreditTransaction:
        """Credit ``amount`` back to the user (e.g. after a failed evaluation)."""
        user.credit_balance += amount
        tx = CreditTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=user.credit_balance,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def award(
        self,
        user: User,
        amount: int,
        *,
        reason: str = "referral",
        ref_type: str | None = None,
        ref_id: int | None = None,
        note: str | None = None,
    ) -> CreditTransaction:
        """Grant ``amount`` credits to the user and record the ledger entry.

        Used for reward grants such as referral bonuses; unlike ``refund`` this
        carries reward-oriented semantics for the transaction ``reason``.
        """
        user.credit_balance += amount
        tx = CreditTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=user.credit_balance,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
        self.session.add(tx)
        await self.session.flush()
        return tx

    async def claim_daily_login_reward(self, user: User, amount: int = 10) -> tuple[bool, int, int]:
        """Grant the daily login reward once per UTC day."""

        today = datetime.now(UTC).date()
        stmt = (
            select(CreditTransaction)
            .where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.reason == "daily_login",
                CreditTransaction.deleted_at.is_(None),
            )
            .order_by(desc(CreditTransaction.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        if latest is not None:
            latest_created_at = latest.created_at
            if latest_created_at.tzinfo is None:
                latest_created_at = latest_created_at.replace(tzinfo=UTC)
            if latest_created_at.astimezone(UTC).date() == today:
                return False, 0, user.credit_balance

        await self.award(
            user,
            amount,
            reason="daily_login",
            ref_type="user",
            ref_id=user.id,
            note="每日登录奖励",
        )
        await self.session.commit()
        return True, amount, user.credit_balance

    # ------------------------------------------------------------------ #
    # Read helpers  (T049)
    # ------------------------------------------------------------------ #

    async def get_balance(self, user: User) -> CreditBalanceResponse:
        """Return the current balance.  updated_at = latest transaction time."""
        stmt = (
            select(CreditTransaction)
            .where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.deleted_at.is_(None),
            )
            .order_by(desc(CreditTransaction.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        latest = result.scalar_one_or_none()
        updated_at = (
            latest.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
            if latest is not None
            else datetime.now(UTC).isoformat().replace("+00:00", "Z")
        )
        return CreditBalanceResponse(
            balance=user.credit_balance,
            updated_at=updated_at,
        )

    async def list_transactions(
        self,
        user: User,
        *,
        cursor: str | None,
        limit: int,
    ) -> CreditTransactionListResponse:
        """Return paginated credit transactions, newest-first."""
        offset = self._decode_cursor(cursor)
        bounded = max(1, min(limit, 100))

        stmt = (
            select(CreditTransaction)
            .where(
                CreditTransaction.user_id == user.id,
                CreditTransaction.deleted_at.is_(None),
            )
            .order_by(desc(CreditTransaction.created_at))
            .offset(offset)
            .limit(bounded + 1)
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > bounded
        visible = rows[:bounded]
        next_cursor = str(offset + bounded) if has_more else None

        return CreditTransactionListResponse(
            items=[self._to_item(tx) for tx in visible],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if not cursor or not cursor.isdigit():
            return 0
        return int(cursor)

    @staticmethod
    def _to_item(tx: CreditTransaction) -> CreditTransactionItem:
        return CreditTransactionItem(
            id=str(tx.id),
            amount=tx.amount,
            balance_after=tx.balance_after,
            reason=tx.reason,
            ref_type=tx.ref_type,
            ref_id=str(tx.ref_id) if tx.ref_id is not None else None,
            note=tx.note,
            created_at=tx.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )
