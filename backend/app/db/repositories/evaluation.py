from __future__ import annotations

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evaluation import Evaluation
from app.db.repositories.base import BaseRepository


class EvaluationRepository(BaseRepository[Evaluation]):
    """Repository for evaluations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Evaluation)

    async def get_by_id_and_user_id(
        self,
        *,
        evaluation_id: int,
        user_id: int,
    ) -> Evaluation | None:
        """Return one evaluation owned by a user."""

        return cast(
            Evaluation | None,
            await self.session.scalar(
                select(Evaluation).where(
                    Evaluation.id == evaluation_id,
                    Evaluation.user_id == user_id,
                    Evaluation.deleted_at.is_(None),
                )
            ),
        )

    async def count_running_by_user_id(
        self,
        *,
        user_id: int,
        running_statuses: tuple[str, ...] = ("queued", "answering", "generating_report"),
    ) -> int:
        """Return the number of evaluations in a running state for a user."""

        result = await self.session.scalar(
            select(func.count()).select_from(Evaluation).where(
                Evaluation.user_id == user_id,
                Evaluation.status.in_(running_statuses),
                Evaluation.deleted_at.is_(None),
            )
        )
        return result or 0

    async def list_by_user_id(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
        status: str | None = None,
    ) -> list[Evaluation]:
        """Return evaluations owned by a user."""

        query = select(Evaluation).where(
            Evaluation.user_id == user_id,
            Evaluation.deleted_at.is_(None),
        )
        if status is not None:
            query = query.where(Evaluation.status == status)
        result = await self.session.scalars(
            query.order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())
