from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.report import Report
from app.db.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    """Repository for reports."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Report)

    async def get_by_evaluation_id(self, *, evaluation_id: int) -> Report | None:
        """Return the report for a given evaluation."""

        return cast(
            Report | None,
            await self.session.scalar(
                select(Report).where(
                    Report.evaluation_id == evaluation_id,
                    Report.deleted_at.is_(None),
                )
            ),
        )

