from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.survey import SurveyGenerateRequest, SurveyQuestion, SurveyResponse
from app.services.survey_service import SurveyService

router = APIRouter(prefix="/api/v1/surveys", tags=["surveys"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)


@router.post("/generate", response_model=SurveyResponse)
async def generate_survey(
    payload: SurveyGenerateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> SurveyResponse:
    """Generate a mock AI survey from the local seed template."""

    return await SurveyService(session).generate_survey(user=current_user, payload=payload)


@router.get("/{survey_id}", response_model=SurveyResponse)
async def get_survey(
    survey_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> SurveyResponse:
    """Return one survey owned through the current user's evaluation."""

    return await SurveyService(session).get_survey(user=current_user, survey_id=survey_id)


@router.put("/{survey_id}/questions", response_model=SurveyResponse)
async def update_survey_questions(
    survey_id: int,
    questions: list[SurveyQuestion],
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> SurveyResponse:
    """Overwrite survey questions while the evaluation is editable."""

    return await SurveyService(session).update_questions(
        user=current_user,
        survey_id=survey_id,
        questions=questions,
    )
