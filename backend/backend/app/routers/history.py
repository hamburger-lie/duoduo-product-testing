from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.history import HistoryListResponse
from app.services.history_service import HistoryService

router = APIRouter(prefix="/api/v1/history", tags=["history"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)


@router.get("", response_model=HistoryListResponse)
async def list_history(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> HistoryListResponse:
    """Return the current user's history — evaluations with product, survey and report snippets.

    Results are sorted newest-first. Use ``cursor`` + ``has_more`` for pagination.
    """

    return await HistoryService(session).list_history(
        user=current_user,
        cursor=cursor,
        limit=limit,
    )
