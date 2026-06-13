from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.whitepaper import Whitepaper
from app.db.repositories.base import BaseRepository


class WhitepaperRepository(BaseRepository[Whitepaper]):
    """Repository for whitepapers."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Whitepaper)

    async def get_by_evaluation_id(self, *, evaluation_id: int) -> Whitepaper | None:
        """Return the whitepaper for a given evaluation."""

        return cast(
            Whitepaper | None,
            await self.session.scalar(
                select(Whitepaper).where(
                    Whitepaper.evaluation_id == evaluation_id,
                    Whitepaper.deleted_at.is_(None),
                )
            ),
        )
