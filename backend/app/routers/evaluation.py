from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
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
from app.schemas.report import DeepAnalysisResponse
from app.services.evaluation_service import EvaluationService
from app.services.report_service import ReportService

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
    background_tasks: BackgroundTasks,
    _rl: None = gen_rate_limit_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> EvaluationRunResponse:
    """Start persona answering: Phase 1 (status change) in request, Phase 2 (AI) in background."""

    from app.core.config import get_settings
    from app.db.session import get_session_factory

    response = await EvaluationService(session).run_evaluation(
        user=current_user,
        evaluation_id=evaluation_id,
        request_id=getattr(request.state, "request_id", None),
    )

    # For sync mode, kick off the AI work in a background task with its own session
    settings = get_settings()
    if settings.evaluation_run_mode.strip().lower() != "celery":
        user_id = current_user.id
        req_id = getattr(request.state, "request_id", None)

        async def _bg_work() -> None:
            async with get_session_factory()() as bg_session:
                from app.db.repositories.user import UserRepository
                bg_user = await UserRepository(bg_session).get_by_id(user_id)
                if bg_user is None:
                    return
                try:
                    await EvaluationService(bg_session)._run_evaluation_ai_work(
                        user=bg_user,
                        evaluation_id=evaluation_id,
                        request_id=req_id,
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "evaluation_ai_work_failed evaluation_id=%s", evaluation_id
                    )

        background_tasks.add_task(_bg_work)

    return response


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


@router.delete("/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_evaluation(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> None:
    """Soft-delete an evaluation owned by the current user."""

    await EvaluationService(session).delete_evaluation(
        user=current_user,
        evaluation_id=evaluation_id,
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


@router.get("/{evaluation_id}/deep-analysis", response_model=DeepAnalysisResponse)
async def get_deep_analysis(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> DeepAnalysisResponse:
    """Generate a deep-analysis narrative for an evaluation."""

    return await ReportService(session).get_deep_analysis(
        user=current_user,
        evaluation_id=evaluation_id,
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
