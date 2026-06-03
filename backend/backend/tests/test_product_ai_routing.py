from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.schemas.product import ProductCreateRequest
from app.services.product_service import ProductService


class _FakeSettings:
    ai_provider = "deepseek"
    deepseek_model_pro = "deepseek-chat"
    deepseek_model_flash = "deepseek-v4-flash"
    zhipu_api_key = "zhipu-key"
    zhipu_model_vision = "glm-4.6v"
    storage_adapter = "mock"
    backend_base_url = "http://127.0.0.1:8000"
    app_env = "development"
    image_extract_mode = "vision"
    vision_image_max_side = 720
    vision_image_jpeg_quality = 70
    image_extract_timeout_seconds = 120.0
    image_extract_cache_ttl_seconds = 0
    debug_ai_extract = False


class _RecordingAIClient:
    def __init__(self) -> None:
        self.endpoint_id: str | None = None
        self.images: list[str] | None = None

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
    ) -> str:
        self.endpoint_id = endpoint_id
        self.images = images
        return """
        {
          "main_selling_points": ["双抗"],
          "key_ingredients": ["虾青素"],
          "suitable_skin_types": ["混油皮"],
          "target_audience": "关注抗初老的人群",
          "competitive_position": "中端功效精华",
          "category": "护肤",
          "sub_category": "精华液",
          "price": 169
        }
        """

    async def complete(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
    ) -> str:
        self.endpoint_id = endpoint_id
        self.images = images
        return "包装显示这是珀莱雅双抗精华。"

    async def stream(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
    ) -> AsyncIterator[str]:
        if False:
            yield ""


@pytest.mark.asyncio
async def test_text_only_product_understand_uses_deepseek_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg_module

    monkeypatch.setattr(cfg_module, "get_settings", lambda: _FakeSettings())
    client = _RecordingAIClient()
    service = ProductService(session=None, ai_client=client)  # type: ignore[arg-type]

    await service._understand_product_with_ai(
        user=None,  # type: ignore[arg-type]
        payload=ProductCreateRequest(
            name="珀莱雅双抗精华2.0",
            description="主打抗氧化和抗糖化，价格169元，适合混油皮。",
            image_object_keys=["products/test/proya.jpg"],
        ),
    )

    assert client.endpoint_id == "deepseek-v4-flash"
    assert client.images is None


@pytest.mark.asyncio
async def test_image_product_understand_keeps_deepseek_for_structured_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg_module

    monkeypatch.setattr(cfg_module, "get_settings", lambda: _FakeSettings())
    client = _RecordingAIClient()
    service = ProductService(session=None, ai_client=client)  # type: ignore[arg-type]

    await service._understand_product_with_ai(
        user=None,  # type: ignore[arg-type]
        payload=ProductCreateRequest(
            name="珀莱雅双抗精华2.0",
            description="主打抗氧化和抗糖化，价格169元，适合混油皮。",
            image_base64_list=["data:image/jpeg;base64,/9j/4AAQSkZJRg=="],
        ),
    )

    assert client.endpoint_id == "deepseek-v4-flash"
    assert client.images is None
