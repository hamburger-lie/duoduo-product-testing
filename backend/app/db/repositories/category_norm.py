from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.category_norm import CategoryNorm
from app.db.repositories.base import BaseRepository


class CategoryNormRepository(BaseRepository[CategoryNorm]):
    """Repository for category norm pool entries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=CategoryNorm)

    async def get_by_evaluation_id(self, *, evaluation_id: int) -> CategoryNorm | None:
        """Return the norm entry for an evaluation, if recorded."""

        return cast(
            CategoryNorm | None,
            await self.session.scalar(
                select(CategoryNorm).where(
                    CategoryNorm.evaluation_id == evaluation_id,
                    CategoryNorm.deleted_at.is_(None),
                )
            ),
        )

    async def list_category_avgs(
        self,
        *,
        category: str,
        exclude_product_id: int | None = None,
        limit: int = 2000,
    ) -> list[float]:
        """Return intent averages of all norm entries in a category.

        全平台共享（不按 user 过滤）；排除本产品自己的历史评测，
        避免同一产品反复测把自己的百分位刷高。
        """

        query = (
            select(CategoryNorm.intent_avg)
            .where(
                CategoryNorm.category == category,
                CategoryNorm.deleted_at.is_(None),
            )
            .order_by(CategoryNorm.created_at.desc())
            .limit(limit)
        )
        if exclude_product_id is not None:
            query = query.where(CategoryNorm.product_id != exclude_product_id)
        result = await self.session.scalars(query)
        return [float(v) for v in result.all()]
