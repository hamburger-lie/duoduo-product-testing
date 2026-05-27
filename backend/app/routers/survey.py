from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.survey import SurveyGenerateRequest, SurveyQuestion, SurveyResponse
from app.services.survey_service import SurveyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/surveys", tags=["surveys"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
gen_rate_limit_dependency = Depends(RateLimiter("gen"))


def _sse_line(data: dict) -> str:
    """Format a single SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    request: Request,
    _rl: None = gen_rate_limit_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> StreamingResponse:
    """SSE stream for survey generation.

    Pushes progress events while AI generates questions, then a done event
    with the survey_id. The frontend uses this to avoid gateway timeouts
    on long AI generations.

    Events:
        data: {"event":"progress","pct":10,"msg":"正在分析产品信息..."}
        data: {"event":"progress","pct":50,"msg":"AI 正在生成问卷..."}
        data: {"event":"done","survey_id":"123456"}
        data: {"event":"error","msg":"生成失败原因"}
    """

    async def event_generator():
        try:
            # Phase 1: validate inputs
            yield _sse_line({"event": "progress", "pct": 5, "msg": "正在校验参数..."})

            svc = SurveyService(session)

            product_id = svc._parse_id(payload.product_id, field_name="product_id")
            evaluation_id = svc._parse_id(payload.evaluation_id, field_name="evaluation_id")

            product = await svc.products.get_by_id_and_user_id(
                product_id=product_id, user_id=current_user.id,
            )
            if product is None:
                yield _sse_line({"event": "error", "msg": "产品不存在"})
                return

            evaluation = await svc.evaluations.get_by_id_and_user_id(
                evaluation_id=evaluation_id, user_id=current_user.id,
            )
            if evaluation is None:
                yield _sse_line({"event": "error", "msg": "测评不存在"})
                return

            if evaluation.product_id != product.id:
                yield _sse_line({"event": "error", "msg": "产品与测评不匹配"})
                return

            # Return existing survey if already generated
            if evaluation.survey_id is not None:
                existing = await svc.surveys.get_by_id_for_user(
                    survey_id=evaluation.survey_id, user_id=current_user.id,
                )
                if existing is not None:
                    yield _sse_line({
                        "event": "progress", "pct": 100, "msg": "问卷已存在",
                    })
                    yield _sse_line({
                        "event": "done", "survey_id": str(existing.id),
                    })
                    return

            # Phase 2: generate questions with AI
            yield _sse_line({"event": "progress", "pct": 10, "msg": "正在分析产品信息..."})

            # Check if client disconnected
            if await request.is_disconnected():
                return

            yield _sse_line({"event": "progress", "pct": 20, "msg": "AI 正在生成问卷题目..."})

            questions = await svc._build_survey_questions(
                product=product,
                extra_focus=payload.extra_focus,
            )

            if await request.is_disconnected():
                return

            yield _sse_line({"event": "progress", "pct": 80, "msg": "正在保存问卷..."})

            # Phase 3: save to DB
            survey = await svc.surveys.create({
                "evaluation_id": evaluation.id,
                "product_id": product.id,
                "questions": questions,
                "version": 1,
                "generated_by": "ai",
            })
            await session.flush()
            evaluation.survey_id = survey.id
            await session.commit()

            yield _sse_line({"event": "progress", "pct": 100, "msg": "问卷生成完成"})
            yield _sse_line({"event": "done", "survey_id": str(survey.id)})

        except Exception as exc:
            logger.exception("survey_generate_stream_failed")
            msg = str(exc) if str(exc) else "问卷生成失败，请重试"
            yield _sse_line({"event": "error", "msg": msg})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
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
