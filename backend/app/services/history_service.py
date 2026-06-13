from __future__ import annotations

from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.repositories.history import HistoryRepository, HistoryRow
from app.schemas.history import (
    HistoryItem,
    HistoryListResponse,
    HistoryProductSnippet,
    HistoryReportSnippet,
    HistorySurveySnippet,
)


class HistoryService:
    """User history — aggregated view of evaluations with survey & report."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._repo = HistoryRepository(session)

    async def list_history(
        self,
        *,
        user: User,
        cursor: str | None,
        limit: int,
    ) -> HistoryListResponse:
        offset = self._decode_cursor(cursor)
        bounded = max(1, min(limit, 100))

        rows = await self._repo.list_for_user(
            user_id=user.id,
            offset=offset,
            limit=bounded + 1,
        )

        has_more = len(rows) > bounded
        visible = rows[:bounded]
        next_cursor = str(offset + bounded) if has_more else None

        return HistoryListResponse(
            items=[self._to_item(row) for row in visible],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _to_item(self, row: HistoryRow) -> HistoryItem:
        p = row.product
        image_url = (
            p.image_urls[0]
            if p.image_urls and len(p.image_urls) > 0
            else None
        )

        survey_snippet: HistorySurveySnippet | None = None
        if row.survey is not None:
            questions = row.survey.questions or []
            survey_snippet = HistorySurveySnippet(
                id=str(row.survey.id),
                question_count=len(questions),
                version=row.survey.version or 1,
            )

        report_snippet: HistoryReportSnippet | None = None
        if row.report is not None:
            summary = row.report.summary or ""
            report_snippet = HistoryReportSnippet(
                id=str(row.report.id),
                summary=summary[:120] if summary else None,
            )

        e = row.evaluation
        return HistoryItem(
            evaluation_id=str(e.id),
            created_at=e.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            status=e.status,
            progress=e.progress,
            persona_count=row.persona_count,
            product=HistoryProductSnippet(
                id=str(p.id),
                name=p.name or "未命名产品",
                brand=p.brand,
                image_url=image_url,
            ),
            survey=survey_snippet,
            report=report_snippet,
        )

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if not cursor or not cursor.isdigit():
            return 0
        return int(cursor)
