from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.models.plus_order import PlusOrder
from app.db.models.user import User
from app.services.pay_service import (
    PLUS_PRICE_FEN,
    build_wx_pay_params,
    create_prepay_order,
    decrypt_notify,
    upload_shipping_info,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/upgrade", tags=["upgrade"])
current_user_dependency = Depends(get_current_user)
db_session_dependency = Depends(get_db_session)


def ensure_plus_payment_enabled() -> None:
    """Hide Plus payment endpoints when the feature is disabled."""

    if not get_settings().plus_payment_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


plus_payment_enabled_dependency = Depends(ensure_plus_payment_enabled)


@router.post("/plus/order", dependencies=[plus_payment_enabled_dependency])
async def create_plus_order(
    request: Request,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> dict:
    """Create a WeChat Pay JSAPI order for Plus membership. Returns wx.requestPayment params."""
    settings = get_settings()

    if not settings.wechat_mch_id or not settings.wechat_pay_private_key:
        raise HTTPException(status_code=503, detail="支付功能尚未开通，敬请期待")

    if not current_user.openid:
        raise HTTPException(status_code=400, detail="用户 openid 缺失，无法发起支付")

    out_trade_no = f"PLUS{int(datetime.now(UTC).timestamp())}{uuid.uuid4().hex[:8].upper()}"
    notify_base_url = str(request.base_url).rstrip("/")

    try:
        prepay_id = await create_prepay_order(
            openid=current_user.openid,
            out_trade_no=out_trade_no,
            notify_base_url=notify_base_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    # Persist pending order record
    order = PlusOrder(
        user_id=current_user.id,
        out_trade_no=out_trade_no,
        amount_fen=PLUS_PRICE_FEN,
        status="pending",
    )
    session.add(order)
    await session.commit()

    params = build_wx_pay_params(prepay_id)
    return {"out_trade_no": out_trade_no, **params}


@router.get("/plus/orders", dependencies=[plus_payment_enabled_dependency])
async def list_plus_orders(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> list[dict]:
    """List current user's Plus orders, newest first."""
    result = await session.execute(
        select(PlusOrder)
        .where(PlusOrder.user_id == current_user.id)
        .order_by(PlusOrder.created_at.desc())
        .limit(50)
    )
    orders = result.scalars().all()
    return [
        {
            "id": o.id,
            "out_trade_no": o.out_trade_no,
            "amount_yuan": o.amount_fen / 100,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        }
        for o in orders
    ]


@router.post("/plus/notify", dependencies=[plus_payment_enabled_dependency])
async def wechat_pay_notify(
    request: Request,
    session: AsyncSession = db_session_dependency,
) -> dict:
    """WeChat Pay payment result callback. Activates Plus on successful payment."""
    try:
        body = await request.json()
    except Exception:
        return {"code": "FAIL", "message": "invalid body"}

    event_type = body.get("event_type", "")
    if event_type != "TRANSACTION.SUCCESS":
        return {"code": "SUCCESS", "message": "ignored"}

    try:
        resource = body.get("resource", {})
        transaction = decrypt_notify(resource)
    except Exception as e:
        logger.error("Failed to decrypt WeChat Pay notify: %s", e)
        return {"code": "FAIL", "message": "decrypt error"}

    trade_state = transaction.get("trade_state")
    if trade_state != "SUCCESS":
        logger.info("WeChat Pay notify trade_state=%s, skipping", trade_state)
        return {"code": "SUCCESS", "message": "not success state"}

    openid = transaction.get("payer", {}).get("openid")
    if not openid:
        return {"code": "FAIL", "message": "missing openid"}

    result = await session.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("WeChat Pay notify: user not found for openid %s", openid)
        return {"code": "FAIL", "message": "user not found"}

    now = datetime.now(UTC)
    out_trade_no = transaction.get("out_trade_no", "")

    # Update order status
    if out_trade_no:
        order_result = await session.execute(
            select(PlusOrder).where(PlusOrder.out_trade_no == out_trade_no)
        )
        order = order_result.scalar_one_or_none()
        if order:
            order.status = "paid"
            order.paid_at = now

    # Activate or extend Plus membership by 1 year
    already_plus = user.is_plus and user.plus_expires_at and user.plus_expires_at > now
    if already_plus:
        user.plus_expires_at = user.plus_expires_at + timedelta(days=365)
    else:
        user.plus_expires_at = now + timedelta(days=365)
    user.is_plus = True

    # Award 500 credits for Plus purchase
    from app.services.credit_service import CreditService
    await CreditService(session).award(
        user,
        500,
        reason="plus",
        note="Plus会员积分奖励",
    )

    await session.commit()

    logger.info("Plus activated for user %s, expires %s", user.id, user.plus_expires_at)

    # 上报订单到微信订单中心（失败不影响主流程）
    await upload_shipping_info(out_trade_no=out_trade_no, openid=openid)

    return {"code": "SUCCESS", "message": "OK"}
