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
    supports_streaming: bool = field(default=False)
    supports_vision: bool = field(default=False)


class ModelRouter:
    """Maps TaskType to the configured endpoint ID from settings."""

    def __init__(self) -> None:
        from app.core.config import get_settings

        s = get_settings()
        self._routes: dict[TaskType, ModelRoute] = {
            TaskType.PRODUCT_UNDERSTAND: ModelRoute(
                task_type=TaskType.PRODUCT_UNDERSTAND,
                endpoint_id=s.ark_ep_vision_pro,
                supports_vision=True,
            ),
            TaskType.SURVEY_GENERATE: ModelRoute(
                task_type=TaskType.SURVEY_GENERATE,
                endpoint_id=s.ark_ep_doubao_seed_16,
            ),
            TaskType.PERSONA_ANSWER: ModelRoute(
                task_type=TaskType.PERSONA_ANSWER,
                endpoint_id=s.ark_ep_doubao_15_pro_character,
            ),
            TaskType.PERSONA_CHAT: ModelRoute(
                task_type=TaskType.PERSONA_CHAT,
                endpoint_id=s.ark_ep_doubao_15_lite,
                supports_streaming=True,
            ),
            TaskType.REPORT_SYNTHESIZE: ModelRoute(
                task_type=TaskType.REPORT_SYNTHESIZE,
                endpoint_id=s.ark_ep_doubao_seed_16,
            ),
            TaskType.MEMORY_EXTRACT: ModelRoute(
                task_type=TaskType.MEMORY_EXTRACT,
                endpoint_id=s.ark_ep_doubao_15_lite,
            ),
        }

    def get(self, task_type: TaskType) -> ModelRoute:
        """Return the route for a task, raising if the endpoint is unconfigured."""

        from app.ai.exceptions import AIServiceUnavailable

        route = self._routes[task_type]
        if not route.endpoint_id:
            raise AIServiceUnavailable(
                f"No endpoint configured for task '{task_type.value}'. "
                f"Set the corresponding ARK_EP_* environment variable."
            )
        return route
