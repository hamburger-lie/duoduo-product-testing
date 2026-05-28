from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.db.models.credit import CreditRechargeOrder, CreditTransaction
from app.db.models.user import User
from app.main import app

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@dataclass
class CreditContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def ctx() -> AsyncIterator[CreditContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(CreditTransaction.__table__.create)
        await conn.run_sync(CreditRechargeOrder.__table__.create)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield CreditContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(ctx: CreditContext, code: str) -> str:
    r = await ctx.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert r.status_code == 200
    return str(r.json()["token"])


# ------------------------------------------------------------------ #
# Tests — auth guard
# ------------------------------------------------------------------ #


async def test_balance_requires_auth(ctx: CreditContext) -> None:
    r = await ctx.client.get("/api/v1/credits/balance")
    assert r.status_code == 401


async def test_transactions_requires_auth(ctx: CreditContext) -> None:
    r = await ctx.client.get("/api/v1/credits/transactions")
    assert r.status_code == 401


# ------------------------------------------------------------------ #
# Tests — balance
# ------------------------------------------------------------------ #


async def test_balance_new_user_is_1000(ctx: CreditContext) -> None:
    token = await _login(ctx, "credit_balance_new")
    r = await ctx.client.get(
        "/api/v1/credits/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 1000
    assert "updated_at" in body


# ------------------------------------------------------------------ #
# Tests — transactions
# ------------------------------------------------------------------ #


async def test_transactions_empty_for_new_user(ctx: CreditContext) -> None:
    """New user has no transactions unless seeded."""
    token = await _login(ctx, "credit_tx_empty")
    r = await ctx.client.get(
        "/api/v1/credits/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_transactions_seeded(ctx: CreditContext) -> None:
    """Transactions we insert are visible through the API."""
    token = await _login(ctx, "credit_tx_seed")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    # Insert 3 transactions directly
    async with ctx.session_factory() as session:
        for i in range(3):
            tx = CreditTransaction(
                user_id=user_id,
                amount=-(i + 1),
                balance_after=1000 - (i + 1),
                reason="persona_answer",
                ref_type="evaluation",
                ref_id=100 + i,
                note=f"角色答题 {i}",
            )
            session.add(tx)
        await session.commit()

    r = await ctx.client.get(
        "/api/v1/credits/transactions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 3
    item = body["items"][0]
    assert item["reason"] == "persona_answer"
    assert item["amount"] < 0
    assert item["balance_after"] is not None
    assert "created_at" in item


async def test_transactions_pagination(ctx: CreditContext) -> None:
    """Cursor pagination works for credit transactions."""
    token = await _login(ctx, "credit_tx_pages")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    async with ctx.session_factory() as session:
        for i in range(5):
            tx = CreditTransaction(
                user_id=user_id,
                amount=-1,
                balance_after=999 - i,
                reason="chat",
            )
            session.add(tx)
        await session.commit()

    r1 = await ctx.client.get(
        "/api/v1/credits/transactions?limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["has_more"] is True
    cursor = body1["next_cursor"]
    assert cursor is not None

    r2 = await ctx.client.get(
        f"/api/v1/credits/transactions?limit=2&cursor={cursor}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body2 = r2.json()
    assert len(body2["items"]) == 2
    assert body2["has_more"] is True

    r3 = await ctx.client.get(
        f"/api/v1/credits/transactions?limit=2&cursor={body2['next_cursor']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    body3 = r3.json()
    assert len(body3["items"]) == 1
    assert body3["has_more"] is False


async def test_transactions_isolation(ctx: CreditContext) -> None:
    """User A cannot see User B's transactions."""
    token_a = await _login(ctx, "credit_iso_a")
    token_b = await _login(ctx, "credit_iso_b")

    me_b = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"}
    )
    user_b_id = int(me_b.json()["id"])

    async with ctx.session_factory() as session:
        tx = CreditTransaction(
            user_id=user_b_id,
            amount=-5,
            balance_after=995,
            reason="survey_gen",
        )
        session.add(tx)
        await session.commit()

    r = await ctx.client.get(
        "/api/v1/credits/transactions",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.json()["items"] == []


# ------------------------------------------------------------------ #
# Tests — recharge
# ------------------------------------------------------------------ #


async def test_recharge_creates_pending_order(ctx: CreditContext) -> None:
    token = await _login(ctx, "credit_recharge_create")
    r = await ctx.client.post(
        "/api/v1/credits/recharge",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-1"},
        json={"amount_yuan": "9.90", "credits": 990, "provider": "manual"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["credits"] == 990
    assert body["amount_yuan"] == "9.90"
    assert body["order_no"].startswith("rch_")


async def test_recharge_idempotency_key_returns_same_order(ctx: CreditContext) -> None:
    token = await _login(ctx, "credit_recharge_idem")
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-same"}
    payload = {"amount_yuan": "19.90", "credits": 1990, "provider": "manual"}

    first = await ctx.client.post("/api/v1/credits/recharge", headers=headers, json=payload)
    second = await ctx.client.post("/api/v1/credits/recharge", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["order_no"] == first.json()["order_no"]


async def test_recharge_callback_settles_once(
    ctx: CreditContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECHARGE_CALLBACK_SECRET", "test-recharge-secret")
    get_settings.cache_clear()
    token = await _login(ctx, "credit_recharge_callback")
    created = await ctx.client.post(
        "/api/v1/credits/recharge",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "idem-cb"},
        json={"amount_yuan": "9.90", "credits": 990, "provider": "manual"},
    )
    assert created.status_code == 200
    payload = {
        "order_no": created.json()["order_no"],
        "provider_transaction_id": "provider-tx-1",
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(
        b"test-recharge-secret",
        body,
        hashlib.sha256,
    ).hexdigest()

    try:
        first = await ctx.client.post(
            "/api/v1/credits/recharge/callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Recharge-Signature": signature,
            },
        )
        second = await ctx.client.post(
            "/api/v1/credits/recharge/callback",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Recharge-Signature": signature,
            },
        )
    finally:
        get_settings.cache_clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "paid"
    assert second.json()["status"] == "paid"

    balance = await ctx.client.get(
        "/api/v1/credits/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert balance.json()["balance"] == 1990
    async with ctx.session_factory() as session:
        from sqlalchemy import select

        txs = (
            await session.scalars(
                select(CreditTransaction).where(CreditTransaction.reason == "recharge")
            )
        ).all()
        assert len(txs) == 1
        assert txs[0].amount == 990


async def test_recharge_callback_rejects_bad_signature(
    ctx: CreditContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECHARGE_CALLBACK_SECRET", "test-recharge-secret")
    get_settings.cache_clear()
    token = await _login(ctx, "credit_recharge_bad_sig")
    created = await ctx.client.post(
        "/api/v1/credits/recharge",
        headers={"Authorization": f"Bearer {token}"},
        json={"amount_yuan": "9.90", "credits": 990, "provider": "manual"},
    )
    payload = {
        "order_no": created.json()["order_no"],
        "provider_transaction_id": "provider-tx-bad",
    }

    try:
        rejected = await ctx.client.post(
            "/api/v1/credits/recharge/callback",
            json=payload,
            headers={"X-Recharge-Signature": "bad"},
        )
    finally:
        get_settings.cache_clear()

    assert rejected.status_code == 401
    assert rejected.json()["code"] == "INVALID_RECHARGE_SIGNATURE"
    balance = await ctx.client.get(
        "/api/v1/credits/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert balance.json()["balance"] == 1000


# ------------------------------------------------------------------ #
# Tests — CreditService unit
# ------------------------------------------------------------------ #


async def test_credit_service_deduct_and_refund(ctx: CreditContext) -> None:
    """CreditService.deduct and .refund update balance correctly."""
    from app.services.credit_service import CreditService

    token = await _login(ctx, "credit_svc_unit")
    me = await ctx.client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = int(me.json()["id"])

    async with ctx.session_factory() as session:
        from sqlalchemy import select

        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()

        svc = CreditService(session)
        await svc.deduct(user, 10, reason="survey_gen", note="生成问卷")
        assert user.credit_balance == 990

        await svc.refund(user, 5, note="部分退还")
        assert user.credit_balance == 995

        await session.commit()

    # Verify balance persisted via API
    r = await ctx.client.get(
        "/api/v1/credits/balance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["balance"] == 995


async def test_credit_endpoints_in_openapi(ctx: CreditContext) -> None:
    r = await ctx.client.get("/openapi.json")
    text = r.text
    assert "/api/v1/credits/balance" in text
    assert "/api/v1/credits/transactions" in text
