from __future__ import annotations

import pytest

from app.ai.client import ArkOpenAIClient, MockAIClient
from app.ai.exceptions import AIServiceUnavailable
from app.ai.factory import get_ai_client


def test_factory_returns_mock_when_provider_is_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _settings(provider="mock"))
    client = get_ai_client()
    assert isinstance(client, MockAIClient)


def test_factory_returns_ark_when_provider_is_ark_and_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _settings(provider="ark", key="sk-test"))
    client = get_ai_client()
    assert isinstance(client, ArkOpenAIClient)


def test_factory_ark_raises_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _settings(provider="ark", key=""))
    with pytest.raises(AIServiceUnavailable) as exc_info:
        get_ai_client()
    assert "ARK_API_KEY" in str(exc_info.value)


def test_factory_unknown_provider_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _settings(provider="openai"))
    with pytest.raises(AIServiceUnavailable):
        get_ai_client()


def test_ark_client_can_be_instantiated_without_real_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(
        cfg,
        "get_settings",
        lambda: _settings(provider="ark", key="sk-placeholder"),
    )
    # should not raise, no network call made
    client = ArkOpenAIClient()
    assert client is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _settings:
    def __init__(
        self,
        provider: str = "mock",
        key: str = "",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
    ) -> None:
        self.ai_provider = provider
        self.ark_api_key = key
        self.ark_base_url = base_url
        self.ark_ep_doubao_seed_16 = "ep-seed"
        self.ark_ep_doubao_15_pro_character = "ep-pro"
        self.ark_ep_doubao_15_lite = "ep-lite"
        self.ark_ep_vision_pro = "ep-vision"
        self.ark_ep_embedding = "ep-embed"
