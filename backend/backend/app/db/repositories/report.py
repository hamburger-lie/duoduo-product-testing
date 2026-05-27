from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evaluation import Evaluation
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    """Repository for reports."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Report)

    async def get_by_evaluation_id(
        self,
        *,
        evaluation_id: int,
        include_deleted: bool = False,
    ) -> Report | None:
        """Return the report for a given evaluation."""

        query = select(Report).where(Report.evaluation_id == evaluation_id)
        if not include_deleted:
            query = query.where(Report.deleted_at.is_(None))
        return cast(
            Report | None,
            await self.session.scalar(query),
        )

    async def list_pdfs_by_user_id(self, *, user_id: int) -> list[tuple[Report, str]]:
        """Return generated PDF reports and product names for a user."""

        result = await self.session.execute(
            select(Report, Product.name)
            .join(Evaluation, Evaluation.id == Report.evaluation_id)
            .join(Product, Product.id == Evaluation.product_id)
            .where(
                Evaluation.user_id == user_id,
                Evaluation.deleted_at.is_(None),
                Product.deleted_at.is_(None),
                Report.deleted_at.is_(None),
                Report.pdf_url.is_not(None),
            )
            .order_by(Report.updated_at.desc(), Report.created_at.desc())
        )
        return [(report, product_name or "") for report, product_name in result.all()]

    async def list_pdfs_by_ids_and_user_id(
        self,
        *,
        report_ids: list[int],
        user_id: int,
    ) -> list[Report]:
        """Return generated PDF reports by ID, scoped to a user."""

        if not report_ids:
            return []
        result = await self.session.scalars(
            select(Report)
            .join(Evaluation, Evaluation.id == Report.evaluation_id)
            .where(
                Report.id.in_(report_ids),
                Evaluation.user_id == user_id,
                Evaluation.deleted_at.is_(None),
                Report.deleted_at.is_(None),
                Report.pdf_url.is_not(None),
            )
        )
        return list(result.all())
