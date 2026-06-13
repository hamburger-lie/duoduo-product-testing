from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.ai.exceptions import AIResponseInvalid
from app.ai.json_utils import parse_json_response, validate_required_keys
from app.ai.models import ModelRouter, TaskType
from app.ai.prompt_manager import render_prompt
from app.ai.usage import AIUsage
from app.schemas.product import ProductAiSummary
from app.schemas.survey import QuestionType, SurveyQuestion

if TYPE_CHECKING:
    from app.ai.client import AIClient
    from app.db.models.persona import Persona
    from app.db.models.product import Product
    from app.db.models.survey import Survey
    from app.schemas.product import ProductCreateRequest

logger = logging.getLogger(__name__)


class ProductUnderstandingAdapter:
    """Structured AI adapter for product understanding."""

    def __init__(
        self,
        ai_client: AIClient | None = None,
        vision_client: AIClient | None = None,
    ) -> None:
        self._ai_client = ai_client
        self._vision_client = vision_client

    async def generate_summary(self, *, payload: ProductCreateRequest) -> ProductAiSummary:
        """Generate normalized product understanding output."""

        from app.ai.factory import get_ai_client, get_vision_client

        images = payload.image_base64_list or []
        router = ModelRouter()

        image_description: str | None = None
        if not self._ai_client:
            # Preferred (merged) path: reuse the extract result from the upload
            # step — no second vision call. This is how appearance/raw_text reach
            # the personas in the normal object-keys flow.
            if payload.image_extract is not None:
                image_description = self._describe_from_extract(payload.image_extract)
                if image_description:
                    logger.info(
                        "product_understand_reused_extract product=%s chars=%d",
                        payload.name or "(unnamed)", len(image_description),
                    )
            # Fallback: base64 images supplied directly, no extract context →
            # one guarded vision describe (routes to doubao via get_vision_client).
            elif images:
                from app.ai.vision_client import _VisionConcurrencyGuard

                vision_client = self._vision_client or get_vision_client()
                vision_route = router.get(TaskType.PRODUCT_UNDERSTAND)
                logger.info(
                    "product_vision_describe product=%s images=%d",
                    payload.name or "(unnamed)", len(images),
                )
                async with _VisionConcurrencyGuard():
                    image_description = await vision_client.complete(
                        system=(
                            "你是产品图片识别助手。"
                            "请用中文详细描述图片中所有可见内容：包装设计、产品名称、成分表、"
                            "容量规格、品牌 logo、使用说明、颜色、形状、任何可见文字。"
                            "只描述图片中实际看到的内容，不要推断或联想。"
                        ),
                        user="请描述这些产品图片。",
                        endpoint_id=vision_route.endpoint_id,
                        images=images,
                    )
                logger.info(
                    "product_vision_describe_done chars=%d",
                    len(image_description) if image_description else 0,
                )

        has_images = bool(image_description) or bool(payload.image_object_keys) or bool(images)
        text_client = self._ai_client or get_ai_client()
        text_route = router.get(TaskType.SURVEY_GENERATE)
        product_context: dict[str, object] = {
            "name": payload.name or "",
            "description": payload.description,
            "brand": payload.brand or "",
            "price": float(payload.price) if payload.price is not None else None,
            "target_channel": payload.target_channel or "",
            "image_object_keys": payload.image_object_keys,
            "has_images": has_images,
            "image_count": len(images) or len(payload.image_object_keys),
        }
        if image_description:
            product_context["image_description"] = image_description

        prompt, _, _ = render_prompt(
            "product_understand",
            user_role_type="manufacturer",
            product=product_context,
        )
        logger.info(
            "product_understand_text product=%s has_images=%s endpoint=%s",
            payload.name or "(unnamed)",
            has_images,
            text_route.endpoint_id,
        )

        raw_json = await text_client.complete_json(
            system="你是美妆行业产品调研专家。严格按 JSON schema 输出，不要返回 Markdown。",
            user=prompt,
            endpoint_id=text_route.endpoint_id,
        )
        data = parse_json_response(raw_json)
        if "key_ingredients_or_features" in data:
            data["key_ingredients"] = data.pop("key_ingredients_or_features")
        if "suitable_skin_types_or_users" in data:
            data["suitable_skin_types"] = data.pop("suitable_skin_types_or_users")
        return ProductAiSummary.model_validate(data)

    @staticmethod
    def _describe_from_extract(ctx: object) -> str | None:
        """Build an image_description string from a prior extract result.

        Reuses appearance + raw_text + suggested_description so product
        understanding (and the personas downstream) get the visual info without
        a second vision call.
        """

        parts: list[str] = []
        appearance = getattr(ctx, "appearance", None)
        raw_text = getattr(ctx, "raw_text", None)
        desc = getattr(ctx, "suggested_description", None)
        if appearance:
            parts.append(f"产品外观（视觉识别）：{appearance}")
        if raw_text:
            parts.append(f"图片可见文字：{raw_text}")
        if desc:
            parts.append(f"图片内容描述：{desc}")
        return "\n".join(parts) if parts else None


SURVEY_BATCH_DIMS: dict[int, tuple[str, ...]] = {
    1: (
        "first_impression",
        "purchase_motivation",
        "price_sensitivity",
        "package_appearance",
        "competitor_comparison",
    ),
    2: (
        "usage_scenario",
        "repurchase_intent",
        "nps_recommendation",
        "channel_touchpoint",
        "painpoint_improvement",
    ),
}
SURVEY_QUESTIONS_PER_BATCH = 15


class SurveyGenerationAdapter:
    """Structured AI adapter for survey generation.

    The 30 questions are generated as two parallel 15-question batches
    (dims 1-5 and dims 6-10) to roughly halve wall-clock latency; a
    malformed batch only retries itself instead of the whole survey.
    """

    def __init__(self, ai_client: AIClient | None = None) -> None:
        self._ai_client = ai_client

    async def generate_questions(
        self,
        *,
        product: Product,
        extra_focus: str | None,
    ) -> list[dict[str, Any]]:
        """Generate validated survey questions."""

        import asyncio

        from app.ai.factory import get_ai_client

        ai_client = self._ai_client or get_ai_client()
        route = ModelRouter().get(TaskType.SURVEY_GENERATE)
        product_summary: dict[str, object] = {
            "id": product.id,
            "name": product.name or "",
            "description": product.description or "",
            "category": product.category or "",
            "brand": product.brand or "",
            "price": float(product.price) if product.price is not None else None,
        }
        if product.ai_summary:
            product_summary = {**product_summary, **product.ai_summary}

        first_half, second_half = await asyncio.gather(
            self._generate_batch(
                ai_client=ai_client,
                endpoint_id=route.endpoint_id,
                product=product,
                product_summary=product_summary,
                extra_focus=extra_focus,
                batch=1,
            ),
            self._generate_batch(
                ai_client=ai_client,
                endpoint_id=route.endpoint_id,
                product=product,
                product_summary=product_summary,
                extra_focus=extra_focus,
                batch=2,
            ),
        )
        merged = first_half + second_half
        if len(merged) != 30:
            raise AIResponseInvalid(f"Expected exactly 30 questions, got {len(merged)}")
        # Renumber positionally so ids stay q01-q30 even if a batch misnumbers.
        for index, question in enumerate(merged, start=1):
            question["id"] = f"q{index:02d}"
        return merged

    async def _generate_batch(
        self,
        *,
        ai_client: AIClient,
        endpoint_id: str,
        product: Product,
        product_summary: dict[str, object],
        extra_focus: str | None,
        batch: int,
    ) -> list[dict[str, Any]]:
        """Generate and validate one 15-question half of the survey."""

        prompt, _, _ = render_prompt(
            "survey_generate",
            user_role_type="manufacturer",
            product_ai_summary=product_summary,
            extra_focus=extra_focus or "",
            product={"id": product.id},
            batch=batch,
        )
        from app.core.config import get_settings

        extra_body: dict[str, object] | None = None
        settings = get_settings()
        if settings.ai_provider == "deepseek" and settings.survey_disable_thinking:
            extra_body = {"thinking": {"type": "disabled"}}
        raw_json = await ai_client.complete_json(
            system="你是专业的市场调研问卷设计专家。严格按 JSON schema 输出。",
            user=prompt,
            endpoint_id=endpoint_id,
            extra_body=extra_body,
        )
        data = parse_json_response(raw_json)
        validate_required_keys(data, ["questions"])

        questions_raw = data["questions"]
        if not isinstance(questions_raw, list):
            raise AIResponseInvalid("'questions' must be a list")
        if len(questions_raw) != SURVEY_QUESTIONS_PER_BATCH:
            raise AIResponseInvalid(
                f"Expected exactly {SURVEY_QUESTIONS_PER_BATCH} questions "
                f"in batch {batch}, got {len(questions_raw)}"
            )

        expected_dims = SURVEY_BATCH_DIMS[batch]
        valid_types = {"single", "multi", "scale_1_5", "open"}
        result: list[dict[str, Any]] = []
        for position, q in enumerate(questions_raw):
            if not isinstance(q, dict):
                raise AIResponseInvalid("Each question must be a JSON object")
            raw_type = str(q.get("type", "open"))
            q_type: QuestionType = raw_type if raw_type in valid_types else "open"  # type: ignore[assignment]
            raw_dim = str(q.get("dim", ""))
            # Fall back to the positional dim (3 questions per dim) when the
            # model returns a dim outside this batch's contract.
            dim = raw_dim if raw_dim in expected_dims else expected_dims[position // 3]
            result.append(
                SurveyQuestion(
                    id=str(q.get("id", "")),
                    dim=dim,
                    type=q_type,
                    question=str(q.get("question", "")),
                    options=q.get("options"),
                ).model_dump()
            )
        return result


@dataclass(frozen=True)
class PersonaAnswerGenerationResult:
    """Validated persona answers plus model usage."""

    answers: list[dict[str, object]]
    overall_intent: int
    sentiment: str
    summary_comment: str | None
    thinking_process: str | None
    usage: AIUsage


class PersonaAnswerGenerationAdapter:
    """Structured AI adapter for persona answer generation."""

    def __init__(self, ai_client: AIClient | None = None) -> None:
        self._ai_client = ai_client

    async def generate_answer(
        self,
        *,
        survey: Survey,
        persona: Persona,
        product_summary: dict[str, object],
    ) -> tuple[list[dict[str, object]], int, str, str | None, str | None]:
        """Generate validated persona answer output."""

        result = await self.generate_answer_with_usage(
            survey=survey,
            persona=persona,
            product_summary=product_summary,
        )
        return (
            result.answers,
            result.overall_intent,
            result.sentiment,
            result.summary_comment,
            result.thinking_process,
        )

    async def generate_answer_with_usage(
        self,
        *,
        survey: Survey,
        persona: Persona,
        product_summary: dict[str, object],
    ) -> PersonaAnswerGenerationResult:
        """Generate validated persona answer output with token usage."""

        from app.ai.factory import get_ai_client

        ai_client = self._ai_client or get_ai_client()
        route = ModelRouter().get(TaskType.PERSONA_ANSWER)
        persona_dict: dict[str, object] = {
            "id": persona.id,
            "name": persona.name,
            "age": persona.age,
            "city": persona.city,
            "occupation": persona.occupation,
            "persona_tag": persona.persona_tag or "",
            "is_critical": persona.is_critical,
        }
        if persona.profile:
            persona_dict = {**persona_dict, **persona.profile}

        prompt, _, _ = render_prompt(
            "persona_answer",
            persona=persona_dict,
            product_ai_summary=product_summary,
            survey_questions=survey.questions,
        )
        ai_result = await ai_client.complete_json_with_usage(
            system="你是一名真实的中国消费者，正在参与产品测评问卷。",
            user=prompt,
            endpoint_id=route.endpoint_id,
        )
        raw_json = ai_result.content
        data = parse_json_response(raw_json)
        validate_required_keys(data, ["overall_intent", "sentiment", "answers"])

        raw_intent = data["overall_intent"]
        if not isinstance(raw_intent, (int, float)):
            raise AIResponseInvalid(
                f"overall_intent must be a number, got {type(raw_intent).__name__}"
            )
        overall_intent = max(1, min(5, int(raw_intent)))

        sentiment = str(data.get("sentiment", "neutral"))
        if sentiment not in ("positive", "neutral", "negative"):
            sentiment = "neutral"

        answers_raw = data["answers"]
        if not isinstance(answers_raw, list):
            raise AIResponseInvalid("'answers' must be a list")

        answers: list[dict[str, object]] = []
        for item in answers_raw:
            if isinstance(item, dict):
                answers.append(
                    {
                        "qid": str(item.get("qid", "")),
                        "type": str(item.get("type", "open")),
                        "answer": item.get("answer", ""),
                        "reason": str(item.get("reason_short", item.get("reason", ""))),
                    }
                )

        summary_comment_raw = data.get("summary_comment")
        summary_comment: str | None = str(summary_comment_raw) if summary_comment_raw else None
        thinking_process_raw = data.get("thinking_process")
        thinking_process: str | None = str(thinking_process_raw) if thinking_process_raw else None
        return PersonaAnswerGenerationResult(
            answers=answers,
            overall_intent=overall_intent,
            sentiment=sentiment,
            summary_comment=summary_comment,
            thinking_process=thinking_process,
            usage=ai_result.usage,
        )
