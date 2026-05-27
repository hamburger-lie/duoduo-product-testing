from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.exceptions import AppException
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.credit import CreditBalanceResponse, CreditTransactionListResponse
from app.services.credit_service import CreditService

router = APIRouter(prefix="/api/v1/credits", tags=["credits"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_balance(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> CreditBalanceResponse:
    """Return the authenticated user's current credit balance."""

    return await CreditService(session).get_balance(current_user)


@router.get("/transactions", response_model=CreditTransactionListResponse)
async def list_transactions(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> CreditTransactionListResponse:
    """Return the authenticated user's credit transaction history, newest-first."""

    return await CreditService(session).list_transactions(
        current_user,
        cursor=cursor,
        limit=limit,
    )


@router.post("/recharge")
async def recharge() -> None:
    """Recharge credits — not implemented in MVP."""

    raise AppException(
        code="NOT_IMPLEMENTED",
        message="充值功能暂未开放",
        http_status=status.HTTP_501_NOT_IMPLEMENTED,
    )
