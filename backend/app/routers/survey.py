from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.streaming import sse_event
from app.core.deps import get_db_session
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.survey import SurveyGenerateRequest, SurveyQuestion, SurveyResponse
from app.services.survey_service import SurveyService

router = APIRouter(prefix="/api/v1/surveys", tags=["surveys"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
gen_rate_limit_dependency = Depends(RateLimiter("gen"))


def survey_generation_progress(elapsed_seconds: float) -> tuple[int, str]:
    """Return a moving progress hint while the AI is still generating."""

    seconds = max(0, int(elapsed_seconds))
    if seconds < 8:
        return 24 + seconds * 3, "正在规划调研维度"
    if seconds < 20:
        return 48 + (seconds - 8) * 2, "正在生成调研题目"
    if seconds < 45:
        return 72 + int((seconds - 20) * 0.6), "正在校验题型和选项"
    if seconds < 90:
        return 88 + int((seconds - 45) * 0.2), "正在整理完整问卷"
    return 98, "即将完成，请稍候"


@router.post("/generate", response_model=SurveyResponse)
async def generate_survey(
    payload: SurveyGenerateRequest,
    _rl: None = gen_rate_limit_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> SurveyResponse:
    """Generate a mock AI survey from the local seed template."""

    return await SurveyService(session).generate_survey(user=current_user, payload=payload)


@router.post("/generate-stream")
async def generate_survey_stream(
    payload: SurveyGenerateRequest,
    _rl: None = gen_rate_limit_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> StreamingResponse:
    """Generate a survey and report progress through SSE."""

    async def stream():
        yield sse_event("progress", pct=10, msg="正在分析产品信息")
        started_at = asyncio.get_running_loop().time()
        survey_task = asyncio.create_task(
            SurveyService(session).generate_survey(
                user=current_user,
                payload=payload,
            )
        )
        try:
            while True:
                try:
                    survey = await asyncio.wait_for(
                        asyncio.shield(survey_task),
                        timeout=3,
                    )
                    break
                except TimeoutError:
                    elapsed = asyncio.get_running_loop().time() - started_at
                    pct, msg = survey_generation_progress(elapsed)
                    yield sse_event("progress", pct=pct, msg=msg)
        except Exception as exc:
            from app.core.exceptions import AppException
            code = exc.code if isinstance(exc, AppException) else "INTERNAL_ERROR"
            msg = exc.message if isinstance(exc, AppException) else "问卷生成失败，请重试"
            yield sse_event("error", code=code, msg=msg)
            return
        yield sse_event("progress", pct=100, msg="问卷生成完成")
        yield sse_event("done", survey_id=survey.id)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
