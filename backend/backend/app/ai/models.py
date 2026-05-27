from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    PRODUCT_UNDERSTAND = "product_understand"
    SURVEY_GENERATE = "survey_generate"
    PERSONA_ANSWER = "persona_answer"
    PERSONA_CHAT = "persona_chat"
    REPORT_SYNTHESIZE = "report_synthesize"
    MEMORY_EXTRACT = "memory_extract"


@dataclass(frozen=True)
class ModelRoute:
    task_type: TaskType
    endpoint_id: str
    endpoint_env_name: str
    supports_streaming: bool = field(default=False)
    supports_vision: bool = field(default=False)


class ModelRouter:
    """Maps TaskType to model routes.

    DeepSeek v4 flash 做文本主力，GLM-4.6V 做多模态。
    PRODUCT_UNDERSTAND 走智谱（如有 key），其余走 DeepSeek flash。
    """

    def __init__(self) -> None:
        from app.core.config import get_settings

        s = get_settings()
        provider = getattr(s, "ai_provider", "mock").strip().lower()
        self._routes: dict[TaskType, ModelRoute]

        if provider == "mock":
            self._routes = {
                t: ModelRoute(
                    task_type=t,
                    endpoint_id="mock",
                    endpoint_env_name="MOCK",
                )
                for t in TaskType
            }
            return

        flash = getattr(s, "deepseek_model_flash", "deepseek-v4-flash")

        if provider == "deepseek":
            self._routes = {
                TaskType.SURVEY_GENERATE: ModelRoute(
                    task_type=TaskType.SURVEY_GENERATE,
                    endpoint_id=flash,
                    endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                ),
                TaskType.PERSONA_ANSWER: ModelRoute(
                    task_type=TaskType.PERSONA_ANSWER,
                    endpoint_id=flash,
                    endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                ),
                TaskType.PERSONA_CHAT: ModelRoute(
                    task_type=TaskType.PERSONA_CHAT,
                    endpoint_id=flash,
                    endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                    supports_streaming=True,
                ),
                TaskType.REPORT_SYNTHESIZE: ModelRoute(
                    task_type=TaskType.REPORT_SYNTHESIZE,
                    endpoint_id=flash,
                    endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                ),
                TaskType.MEMORY_EXTRACT: ModelRoute(
                    task_type=TaskType.MEMORY_EXTRACT,
                    endpoint_id=flash,
                    endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                ),
            }

            # 产品理解：优先走智谱 GLM-4.6V（多模态）
            zhipu_key = getattr(s, "zhipu_api_key", "")
            if zhipu_key:
                vision_model = getattr(s, "zhipu_model_vision", "glm-4.6v")
                self._routes[TaskType.PRODUCT_UNDERSTAND] = ModelRoute(
                    task_type=TaskType.PRODUCT_UNDERSTAND,
                    endpoint_id=vision_model,
                    endpoint_env_name="ZHIPU_MODEL_VISION",
                    supports_vision=True,
                )
            else:
                self._routes[TaskType.PRODUCT_UNDERSTAND] = ModelRoute(
                    task_type=TaskType.PRODUCT_UNDERSTAND,
                    endpoint_id=flash,
                    endpoint_env_name="DEEPSEEK_MODEL_FLASH",
                )
        else:
            # ark (deprecated) — 保留向后兼容
            self._routes = {
                TaskType.PRODUCT_UNDERSTAND: ModelRoute(
                    task_type=TaskType.PRODUCT_UNDERSTAND,
                    endpoint_id=s.ark_ep_vision_pro,
                    endpoint_env_name="ARK_EP_VISION_PRO",
                    supports_vision=True,
                ),
                TaskType.SURVEY_GENERATE: ModelRoute(
                    task_type=TaskType.SURVEY_GENERATE,
                    endpoint_id=s.ark_ep_doubao_seed_16,
                    endpoint_env_name="ARK_EP_DOUBAO_SEED_16",
                ),
                TaskType.PERSONA_ANSWER: ModelRoute(
                    task_type=TaskType.PERSONA_ANSWER,
                    endpoint_id=s.ark_ep_doubao_15_pro_character,
                    endpoint_env_name="ARK_EP_DOUBAO_15_PRO_CHARACTER",
                ),
                TaskType.PERSONA_CHAT: ModelRoute(
                    task_type=TaskType.PERSONA_CHAT,
                    endpoint_id=s.ark_ep_doubao_15_lite,
                    endpoint_env_name="ARK_EP_DOUBAO_15_LITE",
                    supports_streaming=True,
                ),
                TaskType.REPORT_SYNTHESIZE: ModelRoute(
                    task_type=TaskType.REPORT_SYNTHESIZE,
                    endpoint_id=s.ark_ep_doubao_seed_16,
                    endpoint_env_name="ARK_EP_DOUBAO_SEED_16",
                ),
                TaskType.MEMORY_EXTRACT: ModelRoute(
                    task_type=TaskType.MEMORY_EXTRACT,
                    endpoint_id=s.ark_ep_doubao_15_lite,
                    endpoint_env_name="ARK_EP_DOUBAO_15_LITE",
                ),
            }

    def get(self, task_type: TaskType) -> ModelRoute:
        """Return the route for a task, raising if the endpoint is unconfigured."""

        from app.ai.exceptions import AIServiceUnavailable

        route = self._routes[task_type]
        if not route.endpoint_id:
            raise AIServiceUnavailable(
                f"No endpoint configured for task '{task_type.value}'. "
                f"Set the corresponding environment variable."
            )
        return route
