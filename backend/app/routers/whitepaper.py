from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user, get_current_user_optional
from app.db.models.user import User
from app.schemas.whitepaper import WhitepaperGenerateRequest, WhitepaperResponse
from app.services.whitepaper_service import WhitepaperService

router = APIRouter(prefix="/api/v1/whitepapers", tags=["whitepapers"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
optional_user_dependency = Depends(get_current_user_optional)


@router.post("/generate", response_model=WhitepaperResponse)
async def generate_whitepaper(
    payload: WhitepaperGenerateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> WhitepaperResponse:
    """Trigger whitepaper generation for an evaluation (idempotent for ready rows)."""

    return await WhitepaperService(session).request_generation(
        user=current_user,
        evaluation_id=payload.evaluation_id,
        product_name=payload.product_name,
        product_description=payload.product_description,
    )


@router.get("/by-evaluation/{evaluation_id}", response_model=WhitepaperResponse)
async def get_whitepaper_by_evaluation(
    evaluation_id: int,
    current_user: User | None = optional_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> WhitepaperResponse:
    """Return the whitepaper for a given evaluation.

    Authentication is optional — whitepapers are shareable.  When a valid token
    is supplied, ownership is verified.  Without a token the row is returned
    as-is (read-only public access via snowflake EID).
    """

    return await WhitepaperService(session).get_by_evaluation(
        user=current_user,
        evaluation_id=evaluation_id,
    )
