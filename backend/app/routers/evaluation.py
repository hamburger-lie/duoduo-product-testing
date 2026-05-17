from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.evaluation import (
    EvaluationAnswerResponse,
    EvaluationAnswerSummaryItem,
    EvaluationCreateRequest,
    EvaluationListResponse,
    EvaluationPersonaUpdateRequest,
    EvaluationResponse,
    EvaluationRunResponse,
)
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
gen_rate_limit_dependency = Depends(RateLimiter("gen"))


@router.post("", response_model=EvaluationResponse)
async def create_evaluation(
    payload: EvaluationCreateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationResponse:
    """Create a pending evaluation for an owned product."""

    return await EvaluationService(session).create_evaluation(
        user=current_user,
        product_id=payload.product_id,
    )


@router.get("", response_model=EvaluationListResponse)
async def list_evaluations(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationListResponse:
    """List evaluations owned by the current user."""

    return await EvaluationService(session).list_evaluations(
        user=current_user,
        cursor=cursor,
        limit=limit,
        status_filter=status_filter,
    )


@router.put("/{evaluation_id}/personas", response_model=EvaluationResponse)
async def update_evaluation_personas(
    evaluation_id: int,
    payload: EvaluationPersonaUpdateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationResponse:
    """Update selected personas for an editable evaluation."""

    return await EvaluationService(session).update_personas(
        user=current_user,
        evaluation_id=evaluation_id,
        persona_ids=payload.persona_ids,
    )


@router.post(
    "/{evaluation_id}/run",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_evaluation(
    evaluation_id: int,
    request: Request,
    _rl: None = gen_rate_limit_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationRunResponse:
    """Start persona answering in sync or Celery mode."""

    return await EvaluationService(session).run_evaluation(
        user=current_user,
        evaluation_id=evaluation_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post("/{evaluation_id}/cancel", response_model=EvaluationResponse)
async def cancel_evaluation(
    evaluation_id: int,
    request: Request,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationResponse:
    """Cancel an evaluation that is not already done."""

    return await EvaluationService(session).cancel_evaluation(
        user=current_user,
        evaluation_id=evaluation_id,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{evaluation_id}/answers", response_model=list[EvaluationAnswerSummaryItem])
async def list_evaluation_answers(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> list[EvaluationAnswerSummaryItem]:
    """Return answer summaries for one evaluation."""

    return await EvaluationService(session).list_answers(
        user=current_user,
        evaluation_id=evaluation_id,
    )


@router.get("/{evaluation_id}/answers/{persona_id}", response_model=EvaluationAnswerResponse)
async def get_evaluation_answer(
    evaluation_id: int,
    persona_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationAnswerResponse:
    """Return one persona's complete answer for an evaluation."""

    return await EvaluationService(session).get_answer(
        user=current_user,
        evaluation_id=evaluation_id,
        persona_id=persona_id,
    )


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationResponse:
    """Return one evaluation owned by the current user."""

    return await EvaluationService(session).get_evaluation(
        user=current_user,
        evaluation_id=evaluation_id,
    )
