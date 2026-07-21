from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.product import Product
from app.db.repositories.category_norm import CategoryNormRepository

logger = logging.getLogger(__name__)

# 品类常模至少需要多少条历史评测才输出百分位；不足时报告标注「常模样本不足」。
MIN_NORM_SAMPLE = 8

# 品类缺失时的兜底桶：这些评测仍然入池（数据不丢），但只和同为未分类的比。
UNCATEGORIZED = "uncategorized"


def midrank_percentile(value: float, pool: list[float]) -> float:
    """Mid-rank 百分位：低于 value 的条目 + 一半打平的条目占比，0-100。

    比「严格小于」更稳健：分数并列很常见（尤其小样本、量表数据），
    mid-rank 保证对称性（把 pool 里每个值算自身百分位，均值恰为 50）。
    """

    if not pool:
        return 50.0
    less = sum(1 for v in pool if v < value)
    equal = sum(1 for v in pool if v == value)
    return round((less + 0.5 * equal) / len(pool) * 100, 1)


class NormService:
    """品类常模池：写入 + 百分位查询。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.norms = CategoryNormRepository(session)

    async def record_evaluation(
        self,
        *,
        evaluation: Evaluation,
        product: Product | None,
        answers: list[Answer],
    ) -> None:
        """评测完成后把聚合分数写入常模池（幂等：同一评测只写一次）。

        调用方负责 commit。任何异常不应阻断评测完成主流程，
        调用处需 try/except 包裹。
        """

        intents = [a.overall_intent for a in answers if a.overall_intent is not None]
        if not intents:
            return
        existing = await self.norms.get_by_evaluation_id(evaluation_id=evaluation.id)
        if existing is not None:
            return

        distribution = {str(s): 0 for s in range(1, 6)}
        for intent in intents:
            if 1 <= intent <= 5:
                distribution[str(intent)] += 1
        category = (product.category if product else None) or UNCATEGORIZED

        await self.norms.create(
            {
                "evaluation_id": evaluation.id,
                "product_id": evaluation.product_id,
                "user_id": evaluation.user_id,
                "category": category,
                "sub_category": product.sub_category if product else None,
                "intent_avg": round(sum(intents) / len(intents), 3),
                "intent_distribution": distribution,
                "sample_size": len(intents),
                "is_benchmark": False,
            }
        )
        logger.info(
            "category_norm_recorded",
            extra={
                "event": "category_norm_recorded",
                "evaluation_id": evaluation.id,
                "category": category,
                "sample_size": len(intents),
            },
        )

    async def category_percentile(
        self,
        *,
        category: str | None,
        product_id: int,
        intent_avg: float,
    ) -> dict[str, object]:
        """返回本品在同品类常模池中的位置。

        status:
          - "ok"            样本充足，percentile 可用
          - "insufficient"  同品类历史评测不足 MIN_NORM_SAMPLE 条
        """

        resolved = category or UNCATEGORIZED
        pool = await self.norms.list_category_avgs(
            category=resolved,
            exclude_product_id=product_id,
        )
        if len(pool) < MIN_NORM_SAMPLE:
            return {
                "category": resolved,
                "status": "insufficient",
                "norm_sample_size": len(pool),
                "norm_avg": round(sum(pool) / len(pool), 2) if pool else None,
                "percentile": None,
                "delta_vs_norm": None,
            }
        norm_avg = round(sum(pool) / len(pool), 2)
        return {
            "category": resolved,
            "status": "ok",
            "norm_sample_size": len(pool),
            "norm_avg": norm_avg,
            "percentile": midrank_percentile(intent_avg, pool),
            "delta_vs_norm": round(intent_avg - norm_avg, 2),
        }
