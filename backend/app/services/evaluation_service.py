from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.survey import Survey
from app.db.models.user import User
from app.db.repositories.answer import AnswerRepository
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.persona import PersonaRepository
from app.db.repositories.product import ProductRepository
from app.db.repositories.survey import SurveyRepository

if TYPE_CHECKING:
    from app.ai.client import AIClient
from app.schemas.evaluation import (
    AnswerItem,
    EvaluationAnswerResponse,
    EvaluationAnswerSummaryItem,
    EvaluationListResponse,
    EvaluationResponse,
    EvaluationRunResponse,
    EvaluationStats,
)

CONTRACT_PERSONA_COUNT_MIN = 5
MVP_LITE_PERSONA_COUNT_MIN = 1
PERSONA_COUNT_MAX = 100
EDITABLE_STATUSES = {"pending", "generating_survey"}
RUNNING_STATUSES = {"answering", "generating_report"}
FINAL_STATUSES = {"done", "canceled"}


def can_run_evaluation(status_value: str) -> bool:
    """Return whether an evaluation may start or restart answering."""

    return status_value not in RUNNING_STATUSES | FINAL_STATUSES


def can_cancel_evaluation(status_value: str) -> bool:
    """Return whether an evaluation may be canceled."""

    return status_value in {"pending", "generating_survey", "answering"}


class EvaluationService:
    """Evaluation use cases with mock-or-AI persona answer generation."""

    def __init__(
        self,
        session: AsyncSession,
        ai_client: AIClient | None = None,
    ) -> None:
        self.session = session
        self.evaluations = EvaluationRepository(session)
        self.products = ProductRepository(session)
        self.personas = PersonaRepository(session)
        self.surveys = SurveyRepository(session)
        self.answers = AnswerRepository(session)
        self._ai_client = ai_client

    async def create_evaluation(self, *, user: User, product_id: str) -> EvaluationResponse:
        """Create a pending evaluation for one owned product."""

        product_id_int = self._parse_id(product_id, field_name="product_id")
        product = await self.products.get_by_id_and_user_id(
            product_id=product_id_int,
            user_id=user.id,
        )
        if product is None:
            raise self._product_not_found(product_id)

        evaluation = await self.evaluations.create(
            {
                "user_id": user.id,
                "product_id": product.id,
                "survey_id": None,
                "selected_persona_ids": [],
                "status": "pending",
                "progress": 0,
                "credit_cost": 0,
            }
        )
        await self.session.commit()
        return self.to_response(evaluation)

    async def get_evaluation(self, *, user: User, evaluation_id: int) -> EvaluationResponse:
        """Return an evaluation owned by the current user."""

        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=evaluation_id,
            user_id=user.id,
        )
        if evaluation is None:
            raise self._evaluation_not_found(evaluation_id)
        answers = await self.answers.list_by_evaluation_id(evaluation_id=evaluation.id)
        return self.to_response(evaluation, answers=answers, include_stats=True)

    async def list_evaluations(
        self,
        *,
        user: User,
        cursor: str | None,
        limit: int,
        status_filter: str | None,
    ) -> EvaluationListResponse:
        """List evaluations owned by the current user."""

        offset = self._decode_cursor(cursor)
        bounded_limit = max(1, min(limit, 100))
        evaluations = await self.evaluations.list_by_user_id(
            user_id=user.id,
            offset=offset,
            limit=bounded_limit + 1,
            status=status_filter,
        )
        has_more = len(evaluations) > bounded_limit
        visible = evaluations[:bounded_limit]
        return EvaluationListResponse(
            items=[self.to_response(evaluation) for evaluation in visible],
            next_cursor=str(offset + bounded_limit) if has_more else None,
            has_more=has_more,
        )

    async def update_personas(
        self,
        *,
        user: User,
        evaluation_id: int,
        persona_ids: list[str],
    ) -> EvaluationResponse:
        """Update selected personas while the evaluation is editable."""

        evaluation = await self._get_owned_evaluation(user=user, evaluation_id=evaluation_id)
        if evaluation.status not in EDITABLE_STATUSES:
            raise self._evaluation_not_editable(evaluation_id)
        if not (MVP_LITE_PERSONA_COUNT_MIN <= len(persona_ids) <= PERSONA_COUNT_MAX):
            raise AppException(
                code="PERSONA_COUNT_INVALID",
                message="Persona count must be between 1 and 100",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={
                    "min": MVP_LITE_PERSONA_COUNT_MIN,
                    "contract_min": CONTRACT_PERSONA_COUNT_MIN,
                    "max": PERSONA_COUNT_MAX,
                },
            )
        parsed_ids = [
            self._parse_id(persona_id, field_name="persona_ids")
            for persona_id in persona_ids
        ]
        for persona_id in parsed_ids:
            persona = await self.personas.get_active_by_id(persona_id=persona_id)
            if persona is None or not self._can_use_persona(user=user, persona=persona):
                raise self._persona_not_found(persona_id)
        evaluation.selected_persona_ids = parsed_ids
        await self.session.commit()
        return self.to_response(evaluation)

    async def run_evaluation(self, *, user: User, evaluation_id: int) -> EvaluationRunResponse:
        """Run an evaluation using sync or Celery mode."""

        from app.core.config import get_settings

        mode = get_settings().evaluation_run_mode.strip().lower()
        if mode == "celery":
            return await self._enqueue_evaluation(user=user, evaluation_id=evaluation_id)
        return await self._run_evaluation_sync(user=user, evaluation_id=evaluation_id)

    async def _run_evaluation_sync(
        self,
        *,
        user: User,
        evaluation_id: int,
    ) -> EvaluationRunResponse:
        """Run the evaluation synchronously for local tests and mock mode."""

        evaluation = await self._get_owned_evaluation(user=user, evaluation_id=evaluation_id)
        if evaluation.status in RUNNING_STATUSES:
            raise self._evaluation_already_running(evaluation_id)
        if not can_run_evaluation(evaluation.status):
            raise self._evaluation_not_editable(evaluation_id)
        if evaluation.survey_id is None or not evaluation.selected_persona_ids:
            raise self._evaluation_not_ready(evaluation_id)
        survey = await self.surveys.get_by_id_for_user(
            survey_id=evaluation.survey_id,
            user_id=user.id,
        )
        if survey is None:
            raise self._evaluation_not_ready(evaluation_id)

        now = datetime.now(UTC)
        self._mark_answering(
            evaluation,
            now=now,
            queued_at=None,
            task_id=None,
            run_mode="sync",
        )
        await self.session.flush()

        product = await self.products.get_by_id_and_user_id(
            product_id=evaluation.product_id,
            user_id=user.id,
        )
        product_summary: dict[str, object] = {
            "id": evaluation.product_id,
            "name": product.name or "" if product else "",
            "description": product.description or "" if product else "",
        }
        if product and product.ai_summary:
            product_summary = {**product_summary, **product.ai_summary}

        for persona_id in evaluation.selected_persona_ids:
            existing = await self.answers.get_by_evaluation_and_persona(
                evaluation_id=evaluation.id,
                persona_id=int(persona_id),
            )
            if existing is not None:
                continue
            persona = await self.personas.get_active_by_id(persona_id=int(persona_id))
            if persona is None or not self._can_use_persona(user=user, persona=persona):
                continue

            answers, overall_intent, sentiment, summary_comment = await self._generate_answer(
                survey=survey,
                persona=persona,
                product_summary=product_summary,
            )

            await self.answers.create(
                {
                    "evaluation_id": evaluation.id,
                    "survey_id": survey.id,
                    "persona_id": persona.id,
                    "answers": answers,
                    "overall_intent": overall_intent,
                    "sentiment": sentiment,
                    "summary_comment": summary_comment,
                    "status": "done",
                    "token_input": 0,
                    "token_output": 0,
                    "cost_yuan": 0,
                }
            )

        self._mark_finished(evaluation, status_value="done")
        await self.session.commit()
        return EvaluationRunResponse(
            id=str(evaluation.id),
            status=evaluation.status,
            progress=evaluation.progress,
            estimated_seconds=0,
            task_id=f"mock_task_{evaluation.id}",
        )

    async def _enqueue_evaluation(
        self,
        *,
        user: User,
        evaluation_id: int,
    ) -> EvaluationRunResponse:
        """Validate and enqueue evaluation answering into Celery."""

        evaluation = await self._get_owned_evaluation(user=user, evaluation_id=evaluation_id)
        if evaluation.status in RUNNING_STATUSES:
            raise self._evaluation_already_running(evaluation_id)
        if not can_run_evaluation(evaluation.status):
            raise self._evaluation_not_editable(evaluation_id)
        if evaluation.survey_id is None or not evaluation.selected_persona_ids:
            raise self._evaluation_not_ready(evaluation_id)

        survey = await self.surveys.get_by_id_for_user(
            survey_id=evaluation.survey_id,
            user_id=user.id,
        )
        if survey is None:
            raise self._evaluation_not_ready(evaluation_id)

        now = datetime.now(UTC)
        self._mark_answering(
            evaluation,
            now=now,
            queued_at=now,
            task_id=evaluation.task_id,
            run_mode=evaluation.run_mode,
        )

        from app.tasks.evaluation_tasks import run_evaluation_task

        task = run_evaluation_task.apply_async(
            args=[evaluation.id, user.id],
            queue="evaluations",
        )
        evaluation.task_id = str(task.id)
        evaluation.run_mode = "celery"
        await self.session.commit()

        return EvaluationRunResponse(
            id=str(evaluation.id),
            status="answering",
            progress=0,
            estimated_seconds=max(30, len(evaluation.selected_persona_ids) * 8),
            task_id=str(task.id),
        )

    async def cancel_evaluation(self, *, user: User, evaluation_id: int) -> EvaluationResponse:
        """Cancel an editable/running evaluation."""

        evaluation = await self._get_owned_evaluation(user=user, evaluation_id=evaluation_id)
        if evaluation.status == "done":
            raise self._evaluation_not_editable(evaluation_id)
        if can_cancel_evaluation(evaluation.status):
            if evaluation.task_id:
                from app.tasks.celery_app import celery_app

                celery_app.control.revoke(evaluation.task_id, terminate=False)
            self._mark_finished(evaluation, status_value="canceled")
            await self.session.commit()
        return self.to_response(evaluation)

    async def list_answers(
        self,
        *,
        user: User,
        evaluation_id: int,
    ) -> list[EvaluationAnswerSummaryItem]:
        """Return answer summaries for an owned evaluation."""

        evaluation = await self._get_owned_evaluation(user=user, evaluation_id=evaluation_id)
        answers = await self.answers.list_by_evaluation_id(evaluation_id=evaluation.id)
        items: list[EvaluationAnswerSummaryItem] = []
        for answer in answers:
            persona = await self.personas.get_active_by_id(persona_id=answer.persona_id)
            if persona is None:
                continue
            items.append(
                EvaluationAnswerSummaryItem(
                    persona_id=str(answer.persona_id),
                    persona_name=persona.name,
                    persona_tag=persona.persona_tag,
                    overall_intent=answer.overall_intent,
                    sentiment=answer.sentiment,
                    summary_comment=answer.summary_comment,
                )
            )
        return items

    async def get_answer(
        self,
        *,
        user: User,
        evaluation_id: int,
        persona_id: int,
    ) -> EvaluationAnswerResponse:
        """Return one persona's full answer for an owned evaluation."""

        evaluation = await self._get_owned_evaluation(user=user, evaluation_id=evaluation_id)
        answer = await self.answers.get_by_evaluation_and_persona(
            evaluation_id=evaluation.id,
            persona_id=persona_id,
        )
        persona = await self.personas.get_active_by_id(persona_id=persona_id)
        if answer is None or persona is None:
            raise AppException(
                code="RESOURCE_NOT_FOUND",
                message="Answer not found",
                http_status=status.HTTP_404_NOT_FOUND,
                details={"evaluation_id": str(evaluation_id), "persona_id": str(persona_id)},
            )
        return self._answer_to_response(answer=answer, persona=persona)

    def to_response(
        self,
        evaluation: Evaluation,
        *,
        answers: list[Answer] | None = None,
        include_stats: bool = False,
    ) -> EvaluationResponse:
        """Serialize an evaluation with numeric IDs as strings."""

        selected_persona_ids = [str(persona_id) for persona_id in evaluation.selected_persona_ids]
        stats = None
        if include_stats:
            answer_rows = answers or []
            stats = EvaluationStats(
                total_personas=len(selected_persona_ids),
                completed_personas=sum(1 for answer in answer_rows if answer.status == "done"),
                failed_personas=sum(1 for answer in answer_rows if answer.status == "failed"),
            )
        return EvaluationResponse(
            id=str(evaluation.id),
            user_id=str(evaluation.user_id),
            product_id=str(evaluation.product_id),
            survey_id=str(evaluation.survey_id) if evaluation.survey_id is not None else None,
            selected_persona_ids=selected_persona_ids,
            status=evaluation.status,
            progress=evaluation.progress,
            credit_cost=evaluation.credit_cost,
            created_at=self._format_required_dt(evaluation.created_at),
            started_at=self._format_dt(evaluation.started_at),
            finished_at=self._format_dt(evaluation.finished_at),
            error_message=evaluation.error_message,
            stats=stats,
        )

    async def _get_owned_evaluation(self, *, user: User, evaluation_id: int) -> Evaluation:
        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=evaluation_id,
            user_id=user.id,
        )
        if evaluation is None:
            raise self._evaluation_not_found(evaluation_id)
        return evaluation

    # ------------------------------------------------------------------
    # Answer generation: mock vs AI routing
    # ------------------------------------------------------------------

    async def _generate_answer(
        self,
        *,
        survey: Survey,
        persona: Persona,
        product_summary: dict[str, object],
    ) -> tuple[list[dict[str, object]], int, str, str | None]:
        """Route to mock or AI answer generation based on AI_PROVIDER."""

        import logging

        from app.core.config import get_settings

        if get_settings().ai_provider in {"ark", "deepseek"}:
            try:
                return await self._generate_answer_with_ai(
                    survey=survey,
                    persona=persona,
                    product_summary=product_summary,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "persona_answer_ai_failed for persona=%s, falling back to mock",
                    persona.id,
                )

        overall_intent = self._mock_overall_intent(persona)
        return (
            self._build_mock_answers(survey=survey, persona=persona),
            overall_intent,
            self._mock_sentiment(overall_intent),
            None,
        )

    async def _generate_answer_with_ai(
        self,
        *,
        survey: Survey,
        persona: Persona,
        product_summary: dict[str, object],
    ) -> tuple[list[dict[str, object]], int, str, str | None]:
        """Call AI (via persona_answer.j2) to generate one persona's answers."""

        from app.ai.adapters.structured_generation import PersonaAnswerGenerationAdapter

        adapter = PersonaAnswerGenerationAdapter(ai_client=self._ai_client)
        return await adapter.generate_answer(
            survey=survey,
            persona=persona,
            product_summary=product_summary,
        )

    # ------------------------------------------------------------------
    # Mock helpers (unchanged)
    # ------------------------------------------------------------------

    def _build_mock_answers(self, *, survey: Survey, persona: Persona) -> list[dict[str, object]]:
        overall = self._mock_overall_intent(persona)
        answers: list[dict[str, object]] = []
        for index, question in enumerate(survey.questions):
            question_type = str(question["type"])
            options = question.get("options") or []
            answer: int | str | list[str]
            if question_type == "scale_1_5":
                answer = max(1, min(5, overall + (index % 2)))
            elif question_type == "single":
                answer = str(options[index % len(options)]) if options else "其他"
            elif question_type == "multi":
                selected = [str(options[index % len(options)])] if options else ["其他"]
                if len(options) > 1:
                    selected.append(str(options[(index + 1) % len(options)]))
                answer = selected
            else:
                answer = f"{persona.name}认为这款产品整体有亮点，但还需要看真实使用体验。"
            answers.append(
                {
                    "qid": str(question["id"]),
                    "type": question_type,
                    "answer": answer,
                    "reason": f"基于{persona.persona_tag or persona.name}的 mock 判断。",
                }
            )
        return answers

    def _mock_overall_intent(self, persona: Persona) -> int:
        return 3 if persona.is_critical else 4

    def _mock_sentiment(self, overall_intent: int) -> str:
        if overall_intent >= 4:
            return "positive"
        if overall_intent == 3:
            return "neutral"
        return "negative"

    def _mark_answering(
        self,
        evaluation: Evaluation,
        *,
        now: datetime,
        queued_at: datetime | None,
        task_id: str | None,
        run_mode: str | None,
    ) -> None:
        """Move an evaluation into answering state with reset execution fields."""

        evaluation.status = "answering"
        evaluation.progress = 0
        evaluation.started_at = now
        evaluation.queued_at = queued_at
        evaluation.finished_at = None
        evaluation.error_message = None
        evaluation.task_id = task_id
        evaluation.run_mode = run_mode

    def _mark_finished(
        self,
        evaluation: Evaluation,
        *,
        status_value: str,
        error_message: str | None = None,
    ) -> None:
        """Move an evaluation into a terminal state."""

        evaluation.status = status_value
        if status_value == "done":
            evaluation.progress = 100
        evaluation.finished_at = datetime.now(UTC)
        evaluation.error_message = error_message

    def _answer_to_response(self, *, answer: Answer, persona: Persona) -> EvaluationAnswerResponse:
        return EvaluationAnswerResponse(
            evaluation_id=str(answer.evaluation_id),
            persona_id=str(answer.persona_id),
            persona_snapshot=self._persona_snapshot(persona),
            overall_intent=answer.overall_intent,
            sentiment=answer.sentiment,
            summary_comment=answer.summary_comment,
            answers=[AnswerItem(**item) for item in answer.answers],
            created_at=self._format_required_dt(answer.created_at),
        )

    def _persona_snapshot(self, persona: Persona) -> dict[str, object]:
        return {
            "id": str(persona.id),
            "name": persona.name,
            "avatar": persona.avatar,
            "age": persona.age,
            "city": persona.city,
            "occupation": persona.occupation,
            "persona_tag": persona.persona_tag,
            "is_critical": persona.is_critical,
        }

    def _can_use_persona(self, *, user: User, persona: Persona) -> bool:
        return persona.owner_id is None or persona.owner_id == user.id

    def _decode_cursor(self, cursor: str | None) -> int:
        if cursor is None or cursor == "" or not cursor.isdigit():
            return 0
        return int(cursor)

    def _parse_id(self, raw_id: str, *, field_name: str) -> int:
        if not raw_id.isdigit():
            raise AppException(
                code="VALIDATION_ERROR",
                message="ID must be a numeric string",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={field_name: raw_id},
            )
        return int(raw_id)

    def _format_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _format_required_dt(self, value: datetime | None) -> str:
        return self._format_dt(value) or datetime.now(UTC).isoformat().replace("+00:00", "Z")

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

    def _persona_not_found(self, persona_id: int) -> AppException:
        return AppException(
            code="PERSONA_NOT_FOUND",
            message="Persona not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"persona_id": str(persona_id)},
        )

    def _evaluation_not_ready(self, evaluation_id: int) -> AppException:
        return AppException(
            code="EVALUATION_NOT_READY",
            message="Evaluation is missing survey or personas",
            http_status=status.HTTP_400_BAD_REQUEST,
            details={"evaluation_id": str(evaluation_id)},
        )

    def _evaluation_already_running(self, evaluation_id: int) -> AppException:
        return AppException(
            code="EVALUATION_ALREADY_RUNNING",
            message="Evaluation is already running",
            http_status=status.HTTP_409_CONFLICT,
            details={"evaluation_id": str(evaluation_id)},
        )

    def _evaluation_not_editable(self, evaluation_id: int) -> AppException:
        return AppException(
            code="EVALUATION_NOT_EDITABLE",
            message="Evaluation status does not allow this operation",
            http_status=status.HTTP_409_CONFLICT,
            details={"evaluation_id": str(evaluation_id)},
        )
