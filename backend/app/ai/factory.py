from __future__ import annotations

from app.ai.client import AIClient, ArkOpenAIClient, MockAIClient
from app.ai.exceptions import AIServiceUnavailable


def get_ai_client() -> AIClient:
    """Return AI client based on AI_PROVIDER.

    - ``AI_PROVIDER=mock``     → MockAIClient (no key required)
    - ``AI_PROVIDER=deepseek`` → ArkOpenAIClient configured for DeepSeek API
    - ``AI_PROVIDER=ark``      → ArkOpenAIClient for 火山方舟 (DEPRECATED)

    Raises AIServiceUnavailable when credentials are missing.
    """

    from app.core.config import get_settings

    settings = get_settings()
    provider = settings.ai_provider.strip().lower()

    if provider == "mock":
        return MockAIClient()

    if provider == "deepseek":
        if not settings.deepseek_api_key:
            raise AIServiceUnavailable(
                "AI_PROVIDER=deepseek requires DEEPSEEK_API_KEY to be set."
            )
        return ArkOpenAIClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    if provider == "ark":
        # DEPRECATED: 方舟已废弃，保留向后兼容
        if not settings.ark_api_key:
            raise AIServiceUnavailable(
                "AI_PROVIDER=ark requires ARK_API_KEY to be set."
            )
        return ArkOpenAIClient()

    raise AIServiceUnavailable(
        f"Unknown AI_PROVIDER {provider!r}. Valid values: 'mock', 'deepseek', 'ark'."
    )


def get_vision_client() -> AIClient:
    """Return AI client for vision/multimodal tasks (the base64-describe fallback).

    优先豆包（VISION_PROVIDER=doubao + ARK_API_KEY），其次智谱 GLM-4.6V，
    最后 fallback 到 get_ai_client()（纯文本理解）。
    """

    from app.core.config import get_settings

    settings = get_settings()

    if settings.vision_provider.strip().lower() == "doubao" and settings.ark_api_key:
        return ArkOpenAIClient(
            api_key=settings.ark_api_key,
            base_url=settings.ark_base_url,
        )

    if settings.zhipu_api_key:
        return ArkOpenAIClient(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
        )

    # 没有视觉 key，fallback 到默认 client（纯文本理解）
    return get_ai_client()
