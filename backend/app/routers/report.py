from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.report import ReportResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)


@router.get("/by-evaluation/{evaluation_id}", response_model=ReportResponse)
async def get_report_by_evaluation(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ReportResponse:
    """Return or generate a report for a completed evaluation."""

    return await ReportService(session).get_or_create_report(
        user=current_user,
        evaluation_id=evaluation_id,
    )
