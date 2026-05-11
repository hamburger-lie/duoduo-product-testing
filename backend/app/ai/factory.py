from __future__ import annotations

from app.ai.client import AIClient, ArkOpenAIClient, MockAIClient
from app.ai.exceptions import AIServiceUnavailable


def get_ai_client() -> AIClient:
    """Return an AI client based on the AI_PROVIDER setting.

    - ``AI_PROVIDER=mock``  → MockAIClient (no key required)
    - ``AI_PROVIDER=ark``   → ArkOpenAIClient (requires ARK_API_KEY + endpoints)

    Raises AIServiceUnavailable when ``ark`` is selected but credentials are missing.
    """

    from app.core.config import get_settings

    settings = get_settings()
    provider = settings.ai_provider.strip().lower()

    if provider == "mock":
        return MockAIClient()

    if provider == "ark":
        if not settings.ark_api_key:
            raise AIServiceUnavailable(
                "AI_PROVIDER=ark requires ARK_API_KEY to be set. "
                "Set it in .env or use AI_PROVIDER=mock for local development."
            )
        return ArkOpenAIClient()

    raise AIServiceUnavailable(
        f"Unknown AI_PROVIDER {provider!r}. Valid values: 'mock', 'ark'."
    )
