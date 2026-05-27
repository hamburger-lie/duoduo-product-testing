from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.answer import Answer
from app.db.repositories.base import BaseRepository


class AnswerRepository(BaseRepository[Answer]):
    """Repository for answers."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Answer)

    async def get_by_evaluation_and_persona(
        self,
        *,
        evaluation_id: int,
        persona_id: int,
    ) -> Answer | None:
        """Return one answer for an evaluation/persona pair."""

        return cast(
            Answer | None,
            await self.session.scalar(
                select(Answer).where(
                    Answer.evaluation_id == evaluation_id,
                    Answer.persona_id == persona_id,
                    Answer.deleted_at.is_(None),
                )
            )
        )

    async def list_by_evaluation_id(self, *, evaluation_id: int) -> list[Answer]:
        """Return all answers for one evaluation."""

        result = await self.session.scalars(
            select(Answer)
            .where(Answer.evaluation_id == evaluation_id, Answer.deleted_at.is_(None))
            .order_by(Answer.created_at.asc(), Answer.id.asc())
        )
        return list(result.all())
