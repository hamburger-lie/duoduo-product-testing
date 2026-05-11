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
        supports_streaming=True,
    )
    with pytest.raises(AttributeError):
        route.endpoint_id = "other"  # type: ignore[misc]


def test_model_router_raises_when_endpoint_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config as cfg_module

    original = cfg_module.get_settings()

    class _FakeSettings:
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


def test_model_router_returns_route_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config as cfg_module

    original = cfg_module.get_settings()

    class _FakeSettings:
        ark_ep_doubao_seed_16 = "ep-seed"
        ark_ep_doubao_15_pro_character = "ep-pro"
        ark_ep_doubao_15_lite = "ep-lite"
        ark_ep_vision_pro = "ep-vision"
        ark_ep_embedding = "ep-embed"

    monkeypatch.setattr(cfg_module, "get_settings", lambda: _FakeSettings())

    router = ModelRouter()
    route = router.get(TaskType.SURVEY_GENERATE)
    assert route.endpoint_id == "ep-seed"
    assert route.task_type == TaskType.SURVEY_GENERATE

    monkeypatch.setattr(cfg_module, "get_settings", lambda: original)
