from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product
from app.db.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """Repository for products."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Product)

    async def get_by_id_and_user_id(self, *, product_id: int, user_id: int) -> Product | None:
        """Return one product owned by a user."""

        return cast(
            Product | None,
            await self.session.scalar(
                select(Product).where(
                    Product.id == product_id,
                    Product.user_id == user_id,
                    Product.deleted_at.is_(None),
                )
            ),
        )

    async def list_by_user_id(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
    ) -> list[Product]:
        """Return products owned by a user."""

        result = await self.session.scalars(
            select(Product)
            .where(Product.user_id == user_id, Product.deleted_at.is_(None))
            .order_by(Product.created_at.desc(), Product.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())
