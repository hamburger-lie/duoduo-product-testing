from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.credit import (
    CreditBalanceResponse,
    CreditRechargeCallbackRequest,
    CreditRechargeRequest,
    CreditRechargeResponse,
    CreditTransactionListResponse,
)
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


@router.post("/recharge", response_model=CreditRechargeResponse)
async def recharge(
    request: CreditRechargeRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> CreditRechargeResponse:
    """Create a pending provider-neutral recharge order."""

    return await CreditService(session).create_recharge_order(
        current_user,
        request,
        idempotency_key=idempotency_key,
    )


@router.post("/recharge/callback", response_model=CreditRechargeResponse)
async def recharge_callback(
    raw_request: Request,
    signature: str = Header(alias="X-Recharge-Signature"),
    session: AsyncSession = db_session_dependency,
) -> CreditRechargeResponse:
    """Settle a recharge order from a signed internal callback."""

    body = await raw_request.body()
    settings = get_settings()
    CreditService.verify_recharge_callback_signature(
        body,
        signature,
        settings.recharge_callback_secret,
    )
    payload = CreditRechargeCallbackRequest.model_validate_json(body)
    return await CreditService(session).settle_recharge_order(
        payload,
        raw_callback=payload.model_dump(mode="json"),
    )
