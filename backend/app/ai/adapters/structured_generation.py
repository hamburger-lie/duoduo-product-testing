from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.ai.exceptions import AIResponseInvalid
from app.ai.json_utils import parse_json_response, validate_required_keys
from app.ai.models import ModelRouter, TaskType
from app.ai.prompt_manager import render_prompt
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
        has_images = bool(images)
        router = ModelRouter()

        image_description: str | None = None
        if has_images and not self._ai_client:
            vision_client = self._vision_client or get_vision_client()
            vision_route = router.get(TaskType.PRODUCT_UNDERSTAND)
            logger.info(
                "product_vision_describe product=%s images=%d",
                payload.name or "(unnamed)",
                len(images),
            )
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
            "image_count": len(images),
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


class SurveyGenerationAdapter:
    """Structured AI adapter for survey generation."""

    def __init__(self, ai_client: AIClient | None = None) -> None:
        self._ai_client = ai_client

    async def generate_questions(
        self,
        *,
        product: Product,
        extra_focus: str | None,
    ) -> list[dict[str, Any]]:
        """Generate validated survey questions."""

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

        prompt, _, _ = render_prompt(
            "survey_generate",
            user_role_type="manufacturer",
            product_ai_summary=product_summary,
            extra_focus=extra_focus or "",
            product={"id": product.id},
        )
        raw_json = await ai_client.complete_json(
            system="你是专业的市场调研问卷设计专家。严格按 JSON schema 输出。",
            user=prompt,
            endpoint_id=route.endpoint_id,
        )
        data = parse_json_response(raw_json)
        validate_required_keys(data, ["questions"])

        questions_raw = data["questions"]
        if not isinstance(questions_raw, list):
            raise AIResponseInvalid("'questions' must be a list")
        if len(questions_raw) != 30:
            raise AIResponseInvalid(f"Expected exactly 30 questions, got {len(questions_raw)}")

        valid_types = {"single", "multi", "scale_1_5", "open"}
        result: list[dict[str, Any]] = []
        for q in questions_raw:
            if not isinstance(q, dict):
                raise AIResponseInvalid("Each question must be a JSON object")
            raw_type = str(q.get("type", "open"))
            q_type: QuestionType = raw_type if raw_type in valid_types else "open"  # type: ignore[assignment]
            result.append(
                SurveyQuestion(
                    id=str(q.get("id", "")),
                    dim=str(q.get("dim", "unknown")),
                    type=q_type,
                    question=str(q.get("question", "")),
                    options=q.get("options"),
                ).model_dump()
            )
        return result


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
    ) -> tuple[list[dict[str, object]], int, str, str | None]:
        """Generate validated persona answer output."""

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
        raw_json = await ai_client.complete_json(
            system="你是一名真实的中国消费者，正在参与产品测评问卷。",
            user=prompt,
            endpoint_id=route.endpoint_id,
        )
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
        return answers, overall_intent, sentiment, summary_comment
