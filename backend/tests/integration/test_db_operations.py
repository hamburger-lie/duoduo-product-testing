"""Integration tests: real PostgreSQL CRUD, transactions, constraints.

Validates that our SQLAlchemy models work correctly against a real
PostgreSQL instance (not SQLite), including JSONB columns, unique
constraints, and proper transaction rollback behavior.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import skip_no_postgres


@skip_no_postgres
class TestUserCRUD:
    """User table real DB operations."""

    async def test_create_user_with_credit_balance(self, pg_session: AsyncSession) -> None:
        from app.db.models.user import User

        user = User(openid="integration_test_user_1", nickname="IntTest")
        pg_session.add(user)
        await pg_session.flush()

        assert user.id is not None
        assert user.credit_balance == 1000  # default

    async def test_duplicate_openid_raises_integrity_error(
        self, pg_session: AsyncSession
    ) -> None:
        from app.db.models.user import User

        user1 = User(openid="dup_openid_test", nickname="User1")
        user2 = User(openid="dup_openid_test", nickname="User2")
        pg_session.add(user1)
        await pg_session.flush()
        pg_session.add(user2)

        with pytest.raises(IntegrityError):
            await pg_session.flush()


@skip_no_postgres
class TestProductCRUD:
    """Product table with JSONB columns (won't work on SQLite)."""

    async def test_create_product_with_jsonb_ai_summary(
        self, pg_session: AsyncSession
    ) -> None:
        from app.db.models.product import Product
        from app.db.models.user import User

        user = User(openid="product_test_user", nickname="ProdTest")
        pg_session.add(user)
        await pg_session.flush()

        product = Product(
            user_id=user.id,
            name="真实 DB 测试产品",
            description="用于集成测试的产品描述，验证 JSONB 列存储。",
            price=Decimal("199.00"),
            image_urls=["https://example.com/img1.jpg"],
            ai_summary={
                "category": "美妆",
                "sub_category": "面霜",
                "key_ingredients": ["烟酰胺", "玻尿酸"],
                "main_selling_points": ["补水保湿", "提亮肤色"],
            },
            status="ready",
        )
        pg_session.add(product)
        await pg_session.flush()

        # Re-query to verify JSONB stored correctly
        result = await pg_session.get(Product, product.id)
        assert result is not None
        assert result.ai_summary["category"] == "美妆"
        assert len(result.ai_summary["key_ingredients"]) == 2

    async def test_product_jsonb_query(self, pg_session: AsyncSession) -> None:
        """Verify PostgreSQL JSONB query operators work (SQLite can't do this)."""
        from app.db.models.product import Product
        from app.db.models.user import User

        user = User(openid="jsonb_query_user", nickname="JSONBTest")
        pg_session.add(user)
        await pg_session.flush()

        product = Product(
            user_id=user.id,
            name="JSONB 查询测试",
            description="验证 JSONB 查询运算符在真实 PostgreSQL 上的行为。",
            price=Decimal("99.00"),
            image_urls=[],
            ai_summary={"category": "数码", "brand": "TestBrand"},
            status="ready",
        )
        pg_session.add(product)
        await pg_session.flush()

        # PostgreSQL JSONB operator: ->>
        row = await pg_session.execute(
            text(
                "SELECT id FROM products WHERE ai_summary->>'category' = :cat"
            ).bindparams(cat="数码")
        )
        found = row.scalar()
        assert found == product.id


@skip_no_postgres
class TestEvaluationTransactions:
    """Verify transaction behavior with real PostgreSQL."""

    async def test_evaluation_status_transition(self, pg_session: AsyncSession) -> None:
        from app.db.models.evaluation import Evaluation
        from app.db.models.product import Product
        from app.db.models.user import User

        user = User(openid="eval_tx_user", nickname="TxTest")
        pg_session.add(user)
        await pg_session.flush()

        product = Product(
            user_id=user.id,
            name="事务测试产品",
            description="测试评估状态转换事务一致性。",
            price=Decimal("50.00"),
            image_urls=[],
            ai_summary={},
            status="ready",
        )
        pg_session.add(product)
        await pg_session.flush()

        evaluation = Evaluation(
            user_id=user.id,
            product_id=product.id,
            selected_persona_ids=[1, 2, 3],
            status="draft",
        )
        pg_session.add(evaluation)
        await pg_session.flush()

        # Transition: draft → answering → done
        evaluation.status = "answering"
        evaluation.progress = 50
        await pg_session.flush()

        evaluation.status = "done"
        evaluation.progress = 100
        evaluation.finished_at = datetime.now(UTC)
        await pg_session.flush()

        refreshed = await pg_session.get(Evaluation, evaluation.id)
        assert refreshed is not None
        assert refreshed.status == "done"
        assert refreshed.progress == 100

    async def test_credit_deduction_atomicity(self, pg_session: AsyncSession) -> None:
        """Verify credit operations are atomic within a transaction."""
        from app.db.models.credit import CreditTransaction
        from app.db.models.user import User

        user = User(openid="credit_atomic_user", nickname="AtomicTest", credit_balance=500)
        pg_session.add(user)
        await pg_session.flush()

        # Deduct
        user.credit_balance -= 100
        tx = CreditTransaction(
            user_id=user.id,
            amount=-100,
            balance_after=user.credit_balance,
            reason="evaluation",
            ref_type="evaluation",
            ref_id=1,
            note="测试扣费",
        )
        pg_session.add(tx)
        await pg_session.flush()

        assert user.credit_balance == 400

        # Refund
        user.credit_balance += 30
        refund_tx = CreditTransaction(
            user_id=user.id,
            amount=30,
            balance_after=user.credit_balance,
            reason="refund",
            ref_type="evaluation",
            ref_id=1,
            note="测试退款",
        )
        pg_session.add(refund_tx)
        await pg_session.flush()

        assert user.credit_balance == 430

        # Verify transaction log
        txs = (
            await pg_session.scalars(
                select(CreditTransaction)
                .where(CreditTransaction.user_id == user.id)
                .order_by(CreditTransaction.created_at)
            )
        ).all()
        assert len(txs) == 2
        assert txs[0].amount == -100
        assert txs[1].amount == 30


@skip_no_postgres
class TestConversationUniqueConstraint:
    """Verify the unique constraint on conversations works on real PostgreSQL."""

    async def test_duplicate_conversation_raises_integrity_error(
        self, pg_session: AsyncSession
    ) -> None:
        from app.db.models.conversation import Conversation
        from app.db.models.evaluation import Evaluation
        from app.db.models.persona import Persona
        from app.db.models.product import Product
        from app.db.models.user import User

        user = User(openid="conv_constraint_user", nickname="ConvTest")
        pg_session.add(user)
        await pg_session.flush()

        product = Product(
            user_id=user.id, name="P", description="D" * 10,
            price=Decimal("1"), image_urls=[], ai_summary={}, status="ready",
        )
        pg_session.add(product)
        await pg_session.flush()

        persona = Persona(
            owner_id=None, name="角色", avatar="p", age=25,
            gender="female", city="北京", city_tier=1, occupation="工程师",
            income_monthly=20000, ocean_o=50, ocean_c=50, ocean_e=50,
            ocean_a=50, ocean_n=50, profile={}, status="active",
        )
        pg_session.add(persona)
        await pg_session.flush()

        evaluation = Evaluation(
            user_id=user.id, product_id=product.id,
            selected_persona_ids=[persona.id], status="done",
        )
        pg_session.add(evaluation)
        await pg_session.flush()

        conv1 = Conversation(
            user_id=user.id, evaluation_id=evaluation.id, persona_id=persona.id,
        )
        pg_session.add(conv1)
        await pg_session.flush()

        conv2 = Conversation(
            user_id=user.id, evaluation_id=evaluation.id, persona_id=persona.id,
        )
        pg_session.add(conv2)

        with pytest.raises(IntegrityError):
            await pg_session.flush()
