from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models.credit import CreditRechargeOrder, CreditTransaction
from app.db.models.user import User
from app.schemas.credit import (
    CreditBalanceResponse,
    CreditRechargeCallbackRequest,
    CreditRechargeRequest,
    CreditRechargeResponse,
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

    async def create_recharge_order(
        self,
        user: User,
        request: CreditRechargeRequest,
        *,
        idempotency_key: str | None,
    ) -> CreditRechargeResponse:
        """Create or return a pending recharge order for this user."""

        normalized_key = idempotency_key.strip() if idempotency_key else None
        if normalized_key:
            existing = await self.session.scalar(
                select(CreditRechargeOrder).where(
                    CreditRechargeOrder.user_id == user.id,
                    CreditRechargeOrder.idempotency_key == normalized_key,
                    CreditRechargeOrder.deleted_at.is_(None),
                )
            )
            if existing is not None:
                return self._to_recharge_response(existing)

        order = CreditRechargeOrder(
            user_id=user.id,
            order_no=self._generate_order_no(),
            provider=request.provider,
            idempotency_key=normalized_key,
            amount_yuan=request.amount_yuan,
            credits=request.credits,
            status="pending",
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return self._to_recharge_response(order)

    async def settle_recharge_order(
        self,
        request: CreditRechargeCallbackRequest,
        *,
        raw_callback: dict[str, object],
    ) -> CreditRechargeResponse:
        """Mark a pending recharge order paid and credit the user exactly once."""

        duplicate = await self.session.scalar(
            select(CreditRechargeOrder).where(
                CreditRechargeOrder.provider_transaction_id
                == request.provider_transaction_id,
                CreditRechargeOrder.deleted_at.is_(None),
            )
        )
        if duplicate is not None:
            return self._to_recharge_response(duplicate)

        order = await self.session.scalar(
            select(CreditRechargeOrder).where(
                CreditRechargeOrder.order_no == request.order_no,
                CreditRechargeOrder.deleted_at.is_(None),
            )
        )
        if order is None:
            raise AppException(
                code="RESOURCE_NOT_FOUND",
                message="Recharge order not found",
                http_status=status.HTTP_404_NOT_FOUND,
                details={"order_no": request.order_no},
            )

        if order.status == "paid":
            return self._to_recharge_response(order)

        user = await self.session.get(User, order.user_id)
        if user is None:
            raise AppException(
                code="RESOURCE_NOT_FOUND",
                message="Recharge order user not found",
                http_status=status.HTTP_404_NOT_FOUND,
                details={"order_no": request.order_no},
            )

        order.status = "paid"
        order.provider_transaction_id = request.provider_transaction_id
        order.paid_at = request.paid_at or datetime.now(UTC)
        order.raw_callback = raw_callback
        user.credit_balance += order.credits
        tx = CreditTransaction(
            user_id=user.id,
            amount=order.credits,
            balance_after=user.credit_balance,
            reason="recharge",
            ref_type="credit_recharge_order",
            ref_id=order.id,
            note=f"充值订单 {order.order_no}",
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(order)
        return self._to_recharge_response(order)

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

    @staticmethod
    def verify_recharge_callback_signature(
        body: bytes,
        signature: str,
        secret: str,
    ) -> None:
        """Verify HMAC-SHA256 callback signature."""

        if not secret:
            raise AppException(
                code="RECHARGE_SIGNATURE_NOT_CONFIGURED",
                message="Recharge callback signature is not configured",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise AppException(
                code="INVALID_RECHARGE_SIGNATURE",
                message="Invalid recharge callback signature",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

    @staticmethod
    def _generate_order_no() -> str:
        return f"rch_{secrets.token_urlsafe(18)}"

    @staticmethod
    def _to_recharge_response(order: CreditRechargeOrder) -> CreditRechargeResponse:
        return CreditRechargeResponse(
            id=str(order.id),
            order_no=order.order_no,
            provider=order.provider,
            amount_yuan=order.amount_yuan,
            credits=order.credits,
            status=order.status,
            created_at=order.created_at,
            paid_at=order.paid_at,
        )
