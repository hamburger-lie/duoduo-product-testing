from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.credit import CreditTransaction
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app
from app.tasks.evaluation_tasks import _refund_failed_credits


@pytest.fixture
async def credit_client() -> AsyncIterator[AsyncClient]:
    """In-memory SQLite client for credit flow integration tests."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Product.__table__.create)
        await conn.run_sync(Persona.__table__.create)
        await conn.run_sync(Evaluation.__table__.create)
        await conn.run_sync(Survey.__table__.create)
        await conn.run_sync(Answer.__table__.create)
        await conn.run_sync(CreditTransaction.__table__.create)

    # Seed a persona so evaluation tests can select it
    async with session_factory() as session:
        persona = Persona(
            owner_id=None,
            name="测试角色",
            avatar="person",
            age=28,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="产品经理",
            income_monthly=25000,
            ocean_o=70,
            ocean_c=60,
            ocean_e=50,
            ocean_a=65,
            ocean_n=40,
            profile={},
            status="active",
        )
        session.add(persona)
        await session.commit()

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def credit_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """In-memory SQLite session factory for refund ledger tests."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(Product.__table__.create)
        await conn.run_sync(Evaluation.__table__.create)
        await conn.run_sync(CreditTransaction.__table__.create)

    yield session_factory

    await engine.dispose()


async def _login(client: AsyncClient) -> tuple[str, dict[str, str]]:
    """Login and return (token, headers)."""
    resp = await client.post(
        "/api/v1/auth/wechat/login",
        json={"code": "credit_test_user"},
    )
    assert resp.status_code == 200
    token = str(resp.json()["token"])
    return token, {"Authorization": f"Bearer {token}"}


async def _create_product(client: AsyncClient, headers: dict[str, str]) -> str:
    """Create a product and return its ID."""
    resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Test Product",
            "description": "这是一款测试用的数码产品，主打性价比和高性能。",
            "image_object_keys": ["products/2026/05/test_front.jpg"],
        },
        headers=headers,
    )
    assert resp.status_code in {200, 201}
    return str(resp.json()["id"])


async def _setup_evaluation(
    client: AsyncClient, headers: dict[str, str]
) -> tuple[str, list[str]]:
    """Create product, evaluation, select persona, generate survey."""
    product_id = await _create_product(client, headers)

    resp = await client.post(
        "/api/v1/evaluations",
        json={"product_id": product_id},
        headers=headers,
    )
    assert resp.status_code in {200, 201}
    eval_id = resp.json()["id"]

    resp = await client.get("/api/v1/personas", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) > 0, "No personas seeded"
    persona_ids = [resp.json()["items"][0]["id"]]

    resp = await client.put(
        f"/api/v1/evaluations/{eval_id}/personas",
        json={"persona_ids": persona_ids},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/api/v1/surveys/generate",
        json={
            "product_id": product_id,
            "evaluation_id": eval_id,
        },
        headers=headers,
    )
    assert resp.status_code in {200, 201}

    return eval_id, persona_ids


async def _create_charged_evaluation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    balance: int,
    credit_cost: int,
    persona_count: int,
) -> tuple[int, int]:
    """Create a user/evaluation pair that already has credits deducted."""

    async with session_factory() as session:
        user = User(
            openid=f"refund_user_{balance}_{credit_cost}_{persona_count}",
            nickname="Refund User",
            credit_balance=balance,
        )
        session.add(user)
        await session.flush()

        product = Product(
            user_id=user.id,
            name="退款测试产品",
            description="用于测试失败退款的产品",
            price=Decimal("99.00"),
            image_urls=[],
            ai_summary={"category": "测试"},
            status="ready",
        )
        session.add(product)
        await session.flush()

        evaluation = Evaluation(
            user_id=user.id,
            product_id=product.id,
            selected_persona_ids=list(range(1, persona_count + 1)),
            status="answering",
            credit_cost=credit_cost,
        )
        session.add(evaluation)
        await session.commit()
        return user.id, evaluation.id


async def test_credits_deducted_on_run(credit_client: AsyncClient) -> None:
    """Credits should be deducted when evaluation runs successfully."""

    _, headers = await _login(credit_client)

    # Check initial balance
    resp = await credit_client.get("/api/v1/credits/balance", headers=headers)
    assert resp.status_code == 200
    initial_balance = resp.json()["balance"]
    assert initial_balance == 1000

    eval_id, _ = await _setup_evaluation(credit_client, headers)

    # Run evaluation (sync mode, mock AI)
    resp = await credit_client.post(
        f"/api/v1/evaluations/{eval_id}/run",
        headers=headers,
    )
    assert resp.status_code == 202

    # Check balance decreased by 10 (1 persona × 10 credits)
    resp = await credit_client.get("/api/v1/credits/balance", headers=headers)
    new_balance = resp.json()["balance"]
    assert new_balance == initial_balance - 10


async def test_insufficient_credits(credit_client: AsyncClient) -> None:
    """Evaluation run should fail with INSUFFICIENT_CREDITS if balance too low."""

    _, headers = await _login(credit_client)
    eval_id, _ = await _setup_evaluation(credit_client, headers)

    # Patch cost so balance is insufficient (10000 per persona > 1000 balance)
    from app.core.config import get_settings

    real = get_settings()

    class _ExpensiveSettings:
        def __getattr__(self, name: str) -> object:
            if name == "credit_cost_per_persona":
                return 10000
            return getattr(real, name)

    with patch(
        "app.core.config.get_settings",
        return_value=_ExpensiveSettings(),
    ):
        resp = await credit_client.post(
            f"/api/v1/evaluations/{eval_id}/run",
            headers=headers,
        )

    assert resp.status_code == 400
    assert resp.json()["code"] == "INSUFFICIENT_CREDITS"


async def test_no_deduction_when_cost_zero(credit_client: AsyncClient) -> None:
    """When CREDIT_COST_PER_PERSONA=0, no credits should be deducted."""

    _, headers = await _login(credit_client)

    resp = await credit_client.get("/api/v1/credits/balance", headers=headers)
    initial_balance = resp.json()["balance"]

    eval_id, _ = await _setup_evaluation(credit_client, headers)

    from app.core.config import get_settings

    real = get_settings()

    class _FreeSettings:
        def __getattr__(self, name: str) -> object:
            if name == "credit_cost_per_persona":
                return 0
            return getattr(real, name)

    with patch(
        "app.core.config.get_settings",
        return_value=_FreeSettings(),
    ):
        resp = await credit_client.post(
            f"/api/v1/evaluations/{eval_id}/run",
            headers=headers,
        )

    assert resp.status_code == 202

    resp = await credit_client.get("/api/v1/credits/balance", headers=headers)
    assert resp.json()["balance"] == initial_balance


async def test_full_failure_refunds_all_credits(
    credit_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """All failed personas should refund the full deducted evaluation cost."""

    user_id, evaluation_id = await _create_charged_evaluation(
        credit_session_factory,
        balance=970,
        credit_cost=30,
        persona_count=3,
    )

    async with credit_session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        await _refund_failed_credits(
            session=session,
            evaluation=evaluation,
            user_id=user_id,
            failed_count=3,
            total=3,
        )

    async with credit_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.credit_balance == 1000
        transactions = (
            await session.scalars(
                select(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
        ).all()
        assert [tx.amount for tx in transactions] == [30]
        assert transactions[0].reason == "refund"
        assert transactions[0].ref_type == "evaluation"
        assert transactions[0].ref_id == evaluation_id


async def test_partial_failure_refunds_failed_personas_only(
    credit_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Partially failed evaluations should refund failed_count * cost_per_persona."""

    user_id, evaluation_id = await _create_charged_evaluation(
        credit_session_factory,
        balance=970,
        credit_cost=30,
        persona_count=3,
    )

    async with credit_session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        await _refund_failed_credits(
            session=session,
            evaluation=evaluation,
            user_id=user_id,
            failed_count=2,
            total=3,
        )

    async with credit_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.credit_balance == 990
        transactions = (
            await session.scalars(
                select(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
        ).all()
        assert [tx.amount for tx in transactions] == [20]


async def test_successful_evaluation_does_not_refund(
    credit_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A fully successful evaluation should not create a refund transaction."""

    user_id, evaluation_id = await _create_charged_evaluation(
        credit_session_factory,
        balance=970,
        credit_cost=30,
        persona_count=3,
    )

    async with credit_session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        await _refund_failed_credits(
            session=session,
            evaluation=evaluation,
            user_id=user_id,
            failed_count=0,
            total=3,
        )

    async with credit_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.credit_balance == 970
        transactions = (
            await session.scalars(
                select(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
        ).all()
        assert transactions == []


async def test_canceled_evaluation_refunds_uncompleted_personas(
    credit_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Canceled evaluation should refund credits for uncompleted personas."""

    user_id, evaluation_id = await _create_charged_evaluation(
        credit_session_factory,
        balance=970,
        credit_cost=30,
        persona_count=3,
    )

    # Simulate: 1 completed, 2 remaining (canceled before finishing)
    async with credit_session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        await _refund_failed_credits(
            session=session,
            evaluation=evaluation,
            user_id=user_id,
            failed_count=2,  # 2 uncompleted personas
            total=3,
        )

    async with credit_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        # Refunded 2 * 10 = 20, so 970 + 20 = 990
        assert user.credit_balance == 990
        transactions = (
            await session.scalars(
                select(CreditTransaction).where(CreditTransaction.user_id == user_id)
            )
        ).all()
        assert len(transactions) == 1
        assert transactions[0].amount == 20
        assert transactions[0].reason == "refund"
        assert "失败" in (transactions[0].note or "")
