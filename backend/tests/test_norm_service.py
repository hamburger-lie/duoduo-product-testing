"""品类常模池（norm-referenced scoring）单元测试。

覆盖：midrank 百分位纯函数、常模写入幂等性、百分位查询、
样本不足降级、无品类兜底、CategoryNormMetrics schema 校验。
自带内存 SQLite，不依赖外部服务。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.answer import Answer
from app.db.models.category_norm import CategoryNorm
from app.db.models.evaluation import Evaluation
from app.db.models.product import Product
from app.db.models.survey import Survey
from app.db.models.user import User
from app.schemas.report import CategoryNormMetrics
from app.services.norm_service import (
    MIN_NORM_SAMPLE,
    UNCATEGORIZED,
    NormService,
    midrank_percentile,
)


# ---------- 纯函数 ----------


def test_midrank_percentile_empty_pool_returns_midpoint() -> None:
    assert midrank_percentile(3.0, []) == 50.0


def test_midrank_percentile_extremes() -> None:
    assert midrank_percentile(5.0, [1, 2, 3, 4]) == 100.0
    assert midrank_percentile(0.5, [1, 2, 3, 4]) == 0.0


def test_midrank_percentile_all_ties_is_midpoint() -> None:
    assert midrank_percentile(3.0, [3.0, 3.0, 3.0, 3.0]) == 50.0


def test_midrank_percentile_symmetry() -> None:
    """池内每个值对自身池的百分位均值应为 50（mid-rank 的对称性）。"""

    pool = [1.0, 2.0, 3.0, 4.0, 5.0]
    avg = sum(midrank_percentile(v, pool) for v in pool) / len(pool)
    assert abs(avg - 50.0) < 1e-9


# ---------- DB 流程 ----------


@pytest.fixture
async def norm_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        User.__table__,
        Product.__table__,
        Survey.__table__,
        Evaluation.__table__,
        Answer.__table__,
        CategoryNorm.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_evaluation(
    session: AsyncSession,
    svc: NormService,
    *,
    seq: int,
    category: str | None,
    intents: list[int],
) -> Evaluation:
    user = User(openid=f"norm-u{seq}", nickname=f"u{seq}")
    session.add(user)
    await session.flush()
    product = Product(user_id=user.id, description=f"p{seq}", category=category)
    session.add(product)
    await session.flush()
    evaluation = Evaluation(
        user_id=user.id,
        product_id=product.id,
        selected_persona_ids=[],
        status="done",
    )
    session.add(evaluation)
    await session.flush()
    answers = [
        Answer(
            evaluation_id=evaluation.id,
            survey_id=0,
            persona_id=1000 + idx,
            answers=[],
            overall_intent=value,
            sentiment="neutral",
            status="done",
        )
        for idx, value in enumerate(intents)
    ]
    await svc.record_evaluation(evaluation=evaluation, product=product, answers=answers)
    await session.commit()
    return evaluation


async def test_record_evaluation_is_idempotent(norm_session: AsyncSession) -> None:
    svc = NormService(norm_session)
    evaluation = await _seed_evaluation(
        norm_session, svc, seq=1, category="skincare", intents=[4, 4, 4]
    )
    product = await norm_session.get(Product, evaluation.product_id)
    extra = [
        Answer(
            evaluation_id=evaluation.id,
            survey_id=0,
            persona_id=9999,
            answers=[],
            overall_intent=5,
            sentiment="positive",
            status="done",
        )
    ]
    await svc.record_evaluation(evaluation=evaluation, product=product, answers=extra)
    await norm_session.commit()

    pool = await svc.norms.list_category_avgs(category="skincare")
    assert len(pool) == 1


async def test_percentile_ok_when_pool_sufficient(norm_session: AsyncSession) -> None:
    svc = NormService(norm_session)
    for i in range(MIN_NORM_SAMPLE):
        await _seed_evaluation(
            norm_session, svc, seq=10 + i, category="skincare", intents=[3, 3, 3 + i % 3]
        )

    result = await svc.category_percentile(category="skincare", product_id=999_999, intent_avg=4.2)
    assert result["status"] == "ok"
    assert result["norm_sample_size"] == MIN_NORM_SAMPLE
    assert result["percentile"] is not None
    assert 0 <= float(result["percentile"]) <= 100
    CategoryNormMetrics.model_validate(result)


async def test_percentile_excludes_own_product(norm_session: AsyncSession) -> None:
    """同一产品的历史评测不进自己的对比池，避免自我刷分。"""

    svc = NormService(norm_session)
    evaluation = await _seed_evaluation(
        norm_session, svc, seq=30, category="skincare", intents=[5, 5, 5]
    )
    pool = await svc.norms.list_category_avgs(
        category="skincare", exclude_product_id=evaluation.product_id
    )
    assert pool == []


async def test_percentile_insufficient_pool(norm_session: AsyncSession) -> None:
    """牛奶场景：品类池样本不足时不输出百分位，绝对高分不再跨品类误比。"""

    svc = NormService(norm_session)
    await _seed_evaluation(norm_session, svc, seq=40, category="dairy", intents=[5, 5, 5, 5])

    result = await svc.category_percentile(category="dairy", product_id=888_888, intent_avg=4.8)
    assert result["status"] == "insufficient"
    assert result["percentile"] is None
    metrics = CategoryNormMetrics.model_validate(result)
    assert metrics.percentile is None


async def test_uncategorized_fallback_bucket(norm_session: AsyncSession) -> None:
    svc = NormService(norm_session)
    result = await svc.category_percentile(category=None, product_id=1, intent_avg=3.0)
    assert result["category"] == UNCATEGORIZED


async def test_no_answers_records_nothing(norm_session: AsyncSession) -> None:
    svc = NormService(norm_session)
    user = User(openid="norm-empty", nickname="empty")
    norm_session.add(user)
    await norm_session.flush()
    product = Product(user_id=user.id, description="p", category="skincare")
    norm_session.add(product)
    await norm_session.flush()
    evaluation = Evaluation(
        user_id=user.id, product_id=product.id, selected_persona_ids=[], status="done"
    )
    norm_session.add(evaluation)
    await norm_session.flush()

    await svc.record_evaluation(evaluation=evaluation, product=product, answers=[])
    await norm_session.commit()
    assert await svc.norms.get_by_evaluation_id(evaluation_id=evaluation.id) is None
