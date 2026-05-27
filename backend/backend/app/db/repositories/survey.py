from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evaluation import Evaluation
from app.db.models.survey import Survey
from app.db.repositories.base import BaseRepository


class SurveyRepository(BaseRepository[Survey]):
    """Repository for surveys."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Survey)

    async def get_by_id_for_user(self, *, survey_id: int, user_id: int) -> Survey | None:
        """Return one survey through the owning evaluation."""

        return cast(
            Survey | None,
            await self.session.scalar(
                select(Survey)
                .join(Evaluation, Survey.evaluation_id == Evaluation.id)
                .where(
                    Survey.id == survey_id,
                    Evaluation.user_id == user_id,
                    Survey.deleted_at.is_(None),
                    Evaluation.deleted_at.is_(None),
                )
            ),
        )
