from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.models.survey import Survey


@dataclass
class HistoryRow:
    """Flat projection of one history entry — no ORM lazy loading needed."""

    evaluation: Evaluation
    product: Product
    survey: Survey | None
    report: Report | None
    persona_count: int


class HistoryRepository:
    """Read-only queries for the user history page."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
    ) -> list[HistoryRow]:
        """Return history rows, newest first.

        Uses eager loading (joinedload) for product/survey/report so a single
        round-trip to the DB covers everything needed to render the list page.
        The persona_count comes from a correlated subquery so we avoid loading
        all Answer rows.
        """

        # Correlated subquery: count distinct persona answers per evaluation
        persona_count_sq = (
            select(func.count(Answer.id))
            .where(
                Answer.evaluation_id == Evaluation.id,
                Answer.deleted_at.is_(None),
            )
            .correlate(Evaluation)
            .scalar_subquery()
        )

        stmt = (
            select(Evaluation, persona_count_sq.label("persona_count"))
            .where(
                Evaluation.user_id == user_id,
                Evaluation.deleted_at.is_(None),
            )
            .options(
                joinedload(Evaluation.product),
                joinedload(Evaluation.survey),
                joinedload(Evaluation.report),
            )
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
            .offset(offset)
            .limit(limit)
        )

        results = await self.session.execute(stmt)
        rows: list[HistoryRow] = []
        for evaluation, persona_count in results.unique().all():
            rows.append(
                HistoryRow(
                    evaluation=evaluation,
                    product=evaluation.product,
                    survey=evaluation.survey,
                    report=evaluation.report,
                    persona_count=persona_count or 0,
                )
            )
        return rows
