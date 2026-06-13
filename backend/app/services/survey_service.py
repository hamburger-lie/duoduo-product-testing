from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models.survey import Survey
from app.db.models.user import User
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.product import ProductRepository
from app.db.repositories.survey import SurveyRepository
from app.schemas.survey import SurveyGenerateRequest, SurveyQuestion, SurveyResponse

if TYPE_CHECKING:
    from app.ai.client import AIClient
    from app.db.models.product import Product

SURVEY_EDIT_LOCKED_STATUSES = {"answering", "generating_report", "done", "canceled"}
SURVEY_GENERATION_ALLOWED_STATUSES = {"pending", "generating_survey"}


class SurveyService:
    """Survey use cases with mock-or-AI question generation."""

    def __init__(
        self,
        session: AsyncSession,
        ai_client: AIClient | None = None,
    ) -> None:
        self.session = session
        self.surveys = SurveyRepository(session)
        self.evaluations = EvaluationRepository(session)
        self.products = ProductRepository(session)
        self._ai_client = ai_client

    async def generate_survey(
        self,
        *,
        user: User,
        payload: SurveyGenerateRequest,
    ) -> SurveyResponse:
        """Generate or return the existing survey for an evaluation."""

        product_id = self._parse_id(payload.product_id, field_name="product_id")
        evaluation_id = self._parse_id(payload.evaluation_id, field_name="evaluation_id")
        product = await self.products.get_by_id_and_user_id(
            product_id=product_id,
            user_id=user.id,
        )
        if product is None:
            raise self._product_not_found(payload.product_id)

        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=evaluation_id,
            user_id=user.id,
        )
        if evaluation is None:
            raise self._evaluation_not_found(evaluation_id)
        if evaluation.product_id != product.id:
            raise self._product_not_found(payload.product_id)
        if evaluation.survey_id is not None:
            existing = await self.surveys.get_by_id_for_user(
                survey_id=evaluation.survey_id,
                user_id=user.id,
            )
            if existing is not None:
                return self._to_response(existing)
        if evaluation.status not in SURVEY_GENERATION_ALLOWED_STATUSES:
            raise self._evaluation_not_editable(evaluation_id)

        questions = await self._build_survey_questions(
            product=product,
            extra_focus=payload.extra_focus,
        )

        survey = await self.surveys.create(
            {
                "evaluation_id": evaluation.id,
                "product_id": product.id,
                "questions": questions,
                "version": 1,
                "generated_by": "ai",
            }
        )
        await self.session.flush()
        evaluation.survey_id = survey.id
        await self.session.commit()
        return self._to_response(survey)

    async def get_survey(self, *, user: User, survey_id: int) -> SurveyResponse:
        """Return a survey through the current user's evaluation ownership."""

        survey = await self.surveys.get_by_id_for_user(survey_id=survey_id, user_id=user.id)
        if survey is None:
            raise self._survey_not_found(survey_id)
        return self._to_response(survey)

    async def update_questions(
        self,
        *,
        user: User,
        survey_id: int,
        questions: list[SurveyQuestion],
    ) -> SurveyResponse:
        """Overwrite survey questions while the evaluation is still editable."""

        survey = await self.surveys.get_by_id_for_user(survey_id=survey_id, user_id=user.id)
        if survey is None:
            raise self._survey_not_found(survey_id)

        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=survey.evaluation_id,
            user_id=user.id,
        )
        if evaluation is None:
            raise self._survey_not_found(survey_id)
        if evaluation.status in SURVEY_EDIT_LOCKED_STATUSES:
            raise AppException(
                code="SURVEY_LOCKED",
                message="Survey is locked because evaluation has started",
                http_status=status.HTTP_409_CONFLICT,
                details={"survey_id": str(survey_id), "status": evaluation.status},
            )

        await self.surveys.update(
            survey,
            {
                "questions": [question.model_dump() for question in questions],
                "generated_by": "user_edited",
                "version": survey.version + 1,
            },
        )
        await self.session.commit()
        return self._to_response(survey)

    # ------------------------------------------------------------------
    # Question generation: mock vs AI routing
    # ------------------------------------------------------------------

    async def _build_survey_questions(
        self,
        *,
        product: Product,
        extra_focus: str | None,
    ) -> list[dict[str, Any]]:
        """Route to mock or AI generation based on AI_PROVIDER."""

        import logging

        from app.core.config import get_settings

        if get_settings().ai_provider in {"ark", "deepseek"}:
            try:
                timeout = get_settings().survey_ai_timeout_seconds
                return await asyncio.wait_for(
                    self._generate_questions_with_ai(
                        product=product,
                        extra_focus=extra_focus,
                    ),
                    timeout=timeout,
                )
            except TimeoutError as exc:
                logging.getLogger(__name__).warning("survey_ai_generation_timeout")
                raise AppException(
                    code="SURVEY_AI_TIMEOUT",
                    message="DeepSeek 问卷生成超时，请稍后重试",
                    http_status=status.HTTP_504_GATEWAY_TIMEOUT,
                    details={"timeout_seconds": timeout},
                ) from exc
            except Exception as exc:
                logging.getLogger(__name__).exception("survey_ai_generation_failed")
                raise AppException(
                    code="SURVEY_AI_FAILED",
                    message="DeepSeek 问卷生成失败，请稍后重试",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                ) from exc
        return self._generate_mock_questions(extra_focus=extra_focus)

    async def _generate_questions_with_ai(
        self,
        *,
        product: Product,
        extra_focus: str | None,
    ) -> list[dict[str, Any]]:
        """Call AI (via survey_generate.j2) to generate 30 survey questions."""

        from app.ai.adapters.structured_generation import SurveyGenerationAdapter

        adapter = SurveyGenerationAdapter(ai_client=self._ai_client)
        return await adapter.generate_questions(product=product, extra_focus=extra_focus)

    # ------------------------------------------------------------------
    # Mock helpers (unchanged)
    # ------------------------------------------------------------------

    def _generate_mock_questions(self, *, extra_focus: str | None) -> list[dict[str, Any]]:
        questions = self._load_seed_questions()
        if extra_focus and questions:
            questions[-1] = {
                **questions[-1],
                "question": f"{questions[-1]['question']}（可结合：{extra_focus}）",
            }
        return questions

    def _load_seed_questions(self) -> list[dict[str, Any]]:
        template_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "SEEDS"
            / "survey_templates"
            / "beauty_survey_template.json"
        )
        try:
            with template_path.open("r", encoding="utf-8") as file:
                template = json.load(file)
        except FileNotFoundError:
            return self._default_mock_questions()
        raw_questions = template["questions"]
        return [
            SurveyQuestion(
                id=question["id"],
                dim=question["dim"],
                type=question["type"],
                question=question["question"],
                options=question.get("options"),
            ).model_dump()
            for question in raw_questions
        ]

    def _default_mock_questions(self) -> list[dict[str, Any]]:
        return [
            SurveyQuestion(
                id=f"q{i}",
                dim="overall_acceptance",
                type="scale_1_5",
                question=f"请根据你的真实感受，对这个产品的第 {i} 项体验进行 1-5 分评价。",
                options=None,
            ).model_dump()
            for i in range(1, 31)
        ]

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _to_response(self, survey: Survey) -> SurveyResponse:
        return SurveyResponse(
            id=str(survey.id),
            evaluation_id=str(survey.evaluation_id),
            product_id=str(survey.product_id),
            version=survey.version,
            generated_by=survey.generated_by,
            questions=[SurveyQuestion(**question) for question in survey.questions],
            created_at=self._format_dt(survey.created_at),
        )

    def _parse_id(self, raw_id: str, *, field_name: str) -> int:
        if not raw_id.isdigit():
            raise AppException(
                code="VALIDATION_ERROR",
                message="ID must be a numeric string",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={field_name: raw_id},
            )
        return int(raw_id)

    def _format_dt(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _product_not_found(self, product_id: str) -> AppException:
        return AppException(
            code="PRODUCT_NOT_FOUND",
            message="Product not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"product_id": product_id},
        )

    def _evaluation_not_found(self, evaluation_id: int) -> AppException:
        return AppException(
            code="EVALUATION_NOT_FOUND",
            message="Evaluation not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"evaluation_id": str(evaluation_id)},
        )

    def _evaluation_not_editable(self, evaluation_id: int) -> AppException:
        return AppException(
            code="EVALUATION_NOT_EDITABLE",
            message="Evaluation status does not allow survey generation",
            http_status=status.HTTP_409_CONFLICT,
            details={"evaluation_id": str(evaluation_id)},
        )

    def _survey_not_found(self, survey_id: int) -> AppException:
        return AppException(
            code="SURVEY_NOT_FOUND",
            message="Survey not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"survey_id": str(survey_id)},
        )
