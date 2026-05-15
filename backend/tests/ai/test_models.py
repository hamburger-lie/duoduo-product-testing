from __future__ import annotations

import pytest

from app.ai.exceptions import AIServiceUnavailable
from app.ai.models import ModelRoute, ModelRouter, TaskType


def test_task_type_values() -> None:
    expected = {
        "product_understand",
        "survey_generate",
        "persona_answer",
        "persona_chat",
        "report_synthesize",
        "memory_extract",
    }
    assert {t.value for t in TaskType} == expected


def test_model_route_is_frozen() -> None:
    route = ModelRoute(
        task_type=TaskType.PERSONA_CHAT,
        endpoint_id="ep-123",
        endpoint_env_name="ARK_EP_DOUBAO_15_LITE",
        supports_streaming=True,
    )
    with pytest.raises(AttributeError):
        route.endpoint_id = "other"  # type: ignore[misc]


def test_model_router_raises_when_endpoint_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ark provider with empty endpoints should raise AIServiceUnavailable."""
    from app.core import config as cfg_module

    original = cfg_module.get_settings()

    class _FakeSettings:
        ai_provider = "ark"
        ark_ep_doubao_seed_16 = ""
        ark_ep_doubao_15_pro_character = ""
        ark_ep_doubao_15_lite = ""
        ark_ep_vision_pro = ""
        ark_ep_embedding = ""

    monkeypatch.setattr(cfg_module, "get_settings", lambda: _FakeSettings())

    router = ModelRouter()
    with pytest.raises(AIServiceUnavailable):
        router.get(TaskType.PERSONA_CHAT)

    monkeypatch.setattr(cfg_module, "get_settings", lambda: original)


def test_deepseek_router_uses_flash_for_non_vision_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DeepSeek provider should route non-vision tasks to deepseek-v4-flash."""
    from app.core import config as cfg_module

    original = cfg_module.get_settings()

    class _FakeSettings:
        ai_provider = "deepseek"
        deepseek_model_pro = "deepseek-chat"
        deepseek_model_flash = "deepseek-v4-flash"
        zhipu_api_key = ""
        zhipu_model_vision = "glm-4.6v"

    monkeypatch.setattr(cfg_module, "get_settings", lambda: _FakeSettings())

    router = ModelRouter()
    for task_type in TaskType:
        route = router.get(task_type)
        assert route.endpoint_id == "deepseek-v4-flash"
        assert route.endpoint_env_name == "DEEPSEEK_MODEL_FLASH"
        if task_type == TaskType.PERSONA_CHAT:
            assert route.supports_streaming is True

    monkeypatch.setattr(cfg_module, "get_settings", lambda: original)


def test_deepseek_router_keeps_zhipu_for_vision_product_understand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Product understanding should keep the vision route when Zhipu is configured."""
    from app.core import config as cfg_module

    original = cfg_module.get_settings()

    class _FakeSettings:
        ai_provider = "deepseek"
        deepseek_model_pro = "deepseek-chat"
        deepseek_model_flash = "deepseek-v4-flash"
        zhipu_api_key = "zhipu-key"
        zhipu_model_vision = "glm-4.6v"

    monkeypatch.setattr(cfg_module, "get_settings", lambda: _FakeSettings())

    route = ModelRouter().get(TaskType.PRODUCT_UNDERSTAND)
    assert route.endpoint_id == "glm-4.6v"
    assert route.endpoint_env_name == "ZHIPU_MODEL_VISION"
    assert route.supports_vision is True

    monkeypatch.setattr(cfg_module, "get_settings", lambda: original)
