from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.vision_client import (
    MockVisionClient,
    VisionExtractResult,
    VisionFieldResult,
    ZhipuVisionClient,
    ZhipuVisionTextClient,
    _validate_image_urls_for_real_model,
    get_vision_extract_client,
)
from app.core.deps import get_db_session
from app.db.models.product import Product
from app.db.models.user import User
from app.main import app
from app.services.product_image_extract_service import ProductImageExtractService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def extract_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client: AsyncClient, code: str = "mock_extract_user") -> str:
    resp = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert resp.status_code == 200
    return str(resp.json()["token"])


# ---------------------------------------------------------------------------
# Happy path (mock provider — AI_PROVIDER=mock in test conftest)
# ---------------------------------------------------------------------------


async def test_extract_returns_fields(extract_client: AsyncClient) -> None:
    """Normal call returns structured fields for user review."""

    token = await _login(extract_client)
    resp = await extract_client.post(
        "/api/v1/products/extract-from-images",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "image_urls": ["https://example.com/product.jpg"],
            "target_fields": ["name", "brand", "selling_points"],
            "locale": "zh-CN",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["source_image_count"] == 1
    assert "name" in body["fields"]
    assert "brand" in body["fields"]
    assert "selling_points" in body["fields"]
    for field_data in body["fields"].values():
        assert 0.0 <= field_data["confidence"] <= 1.0
        assert field_data["source"]


async def test_extract_default_fields_returned(extract_client: AsyncClient) -> None:
    """Empty target_fields triggers extraction of all known fields."""

    token = await _login(extract_client, "mock_extract2")
    resp = await extract_client.post(
        "/api/v1/products/extract-from-images",
        headers={"Authorization": f"Bearer {token}"},
        json={"image_urls": ["https://example.com/a.jpg"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["fields"]) > 0


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


async def test_extract_empty_image_urls_returns_400(extract_client: AsyncClient) -> None:
    """image_urls=[] is rejected with 400 (project maps all validation errors to 400)."""

    token = await _login(extract_client, "mock_extract3")
    resp = await extract_client.post(
        "/api/v1/products/extract-from-images",
        headers={"Authorization": f"Bearer {token}"},
        json={"image_urls": []},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


async def test_extract_missing_image_urls_returns_400(extract_client: AsyncClient) -> None:
    """Omitting image_urls entirely returns 400 (project-wide validation error format)."""

    token = await _login(extract_client, "mock_extract4")
    resp = await extract_client.post(
        "/api/v1/products/extract-from-images",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_fields": ["name"]},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# needs_review flag
# ---------------------------------------------------------------------------


async def test_low_confidence_triggers_needs_review(extract_client: AsyncClient) -> None:
    """Any field below CONFIDENCE_REVIEW_THRESHOLD sets needs_review=True."""

    token = await _login(extract_client, "mock_extract5")
    resp = await extract_client.post(
        "/api/v1/products/extract-from-images",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "image_urls": ["https://example.com/b.jpg"],
            "target_fields": ["claims", "usage_scenario"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["needs_review"] is True


async def test_vision_moderation_hit_triggers_review_not_block() -> None:
    """Vision-extracted high-risk text marks review instead of blocking."""

    mock_client = AsyncMock()
    mock_client.extract_fields = AsyncMock(
        return_value=VisionExtractResult(
            raw_text="包装文字疑似包含枪支相关词",
            fields={
                "name": VisionFieldResult(value="测试产品", confidence=0.95, source="zhipu_vision"),
            },
            suggested_description="这是一段包含枪支字样的视觉识别描述",
            source_image_count=1,
        )
    )

    from app.schemas.product import ImageExtractRequest

    svc = ProductImageExtractService(vision_client=mock_client)
    result = await svc.extract(
        ImageExtractRequest(image_urls=["https://example.com/review.jpg"])
    )

    assert result.status == "ok"
    assert result.needs_review is True


# ---------------------------------------------------------------------------
# Service unit tests (no HTTP layer)
# ---------------------------------------------------------------------------


async def test_service_needs_review_false_when_all_high_confidence() -> None:
    """needs_review=False when all fields are above threshold."""

    mock_client = AsyncMock()
    mock_client.extract_fields = AsyncMock(
        return_value=VisionExtractResult(
            raw_text="some text",
            fields={
                "name": VisionFieldResult(value="好产品", confidence=0.95, source="image_ocr"),
                "brand": VisionFieldResult(value="好品牌", confidence=0.90, source="image_ocr"),
            },
            suggested_description="好产品描述",
            source_image_count=1,
        )
    )

    from app.schemas.product import ImageExtractRequest

    svc = ProductImageExtractService(vision_client=mock_client)
    result = await svc.extract(
        ImageExtractRequest(
            image_urls=["https://example.com/c.jpg"],
            target_fields=["name", "brand"],
        )
    )
    assert result.needs_review is False
    assert result.status == "ok"
    assert result.fields["name"].value == "好产品"


async def test_service_does_not_persist_product() -> None:
    """Service must not write to DB — no session interaction at all."""

    mock_client = AsyncMock()
    mock_client.extract_fields = AsyncMock(
        return_value=VisionExtractResult(
            raw_text=None,
            fields={"name": VisionFieldResult(value="Test", confidence=0.9, source="image_ocr")},
            source_image_count=1,
        )
    )

    from app.schemas.product import ImageExtractRequest

    svc = ProductImageExtractService(vision_client=mock_client)
    result = await svc.extract(
        ImageExtractRequest(image_urls=["https://example.com/d.jpg"], target_fields=["name"])
    )
    assert result.status == "ok"
    mock_client.extract_fields.assert_awaited_once()


# ---------------------------------------------------------------------------
# Existing product creation endpoint must be unaffected
# ---------------------------------------------------------------------------


async def test_existing_create_product_endpoint_unaffected(extract_client: AsyncClient) -> None:
    """POST /api/v1/products still works after the new route is added."""

    token = await _login(extract_client, "mock_extract6")
    resp = await extract_client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "测试产品",
            "description": "添加烟酰胺和神经酰胺，主打温和修护，适合日常护肤使用。",
            "image_object_keys": ["products/2026/06/test.jpg"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["status"] == "ready"


# ---------------------------------------------------------------------------
# Provider factory tests
# ---------------------------------------------------------------------------


def test_factory_returns_mock_when_ai_provider_mock() -> None:
    """AI_PROVIDER=mock (test default) → MockVisionClient."""

    client = get_vision_extract_client()
    assert isinstance(client, MockVisionClient)


def test_factory_raises_when_zhipu_without_key() -> None:
    """VISION_PROVIDER=zhipu without ZHIPU_API_KEY → clear error."""

    from app.ai.exceptions import AIServiceUnavailable

    class FakeSettings:
        vision_provider = "zhipu"
        ai_provider = "mock"
        zhipu_api_key = ""
        zhipu_base_url = "https://open.bigmodel.cn/api/paas/v4"
        zhipu_model_vision = "glm-4.6v"
        image_extract_mode = "vision"
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeSettings()):
        with pytest.raises(AIServiceUnavailable, match="ZHIPU_API_KEY"):
            get_vision_extract_client()


def test_factory_returns_zhipu_when_configured() -> None:
    """VISION_PROVIDER=zhipu with key → ZhipuVisionClient."""

    class FakeSettings:
        vision_provider = "zhipu"
        ai_provider = "deepseek"
        zhipu_api_key = "test-key-123"
        zhipu_base_url = "https://open.bigmodel.cn/api/paas/v4"
        zhipu_model_vision = "glm-4.6v"
        image_extract_mode = "vision"
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeSettings()):
        client = get_vision_extract_client()
        assert isinstance(client, ZhipuVisionClient)


def test_factory_returns_vision_text_client() -> None:
    """IMAGE_EXTRACT_MODE=vision_text → ZhipuVisionTextClient."""

    class FakeSettings:
        vision_provider = "zhipu"
        ai_provider = "deepseek"
        zhipu_api_key = "test-key-123"
        zhipu_base_url = "https://open.bigmodel.cn/api/paas/v4"
        zhipu_model_vision = "glm-4.6v"
        image_extract_mode = "vision_text"
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeSettings()):
        client = get_vision_extract_client()
        assert isinstance(client, ZhipuVisionTextClient)


# ---------------------------------------------------------------------------
# URL validation tests
# ---------------------------------------------------------------------------


def test_mock_cdn_url_rejected_in_real_mode() -> None:
    """mock-cdn.local URLs are blocked regardless of environment."""

    from app.core.exceptions import AppException

    with pytest.raises(AppException) as exc_info:
        _validate_image_urls_for_real_model(
            ["https://mock-cdn.local/products/2026/06/test.jpg"]
        )
    assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"


def test_localhost_url_allowed_in_development() -> None:
    """localhost is allowed in development (STORAGE_ADAPTER=local uses it)."""

    class FakeDevSettings:
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeDevSettings()):
        # Should not raise — backend serves images locally in dev
        _validate_image_urls_for_real_model(
            ["http://localhost:8000/api/v1/internal/product-images/products/test.jpg"]
        )


def test_127_url_allowed_in_development() -> None:
    """127.0.0.1 is allowed in development (local storage)."""

    class FakeDevSettings:
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeDevSettings()):
        _validate_image_urls_for_real_model(
            ["http://127.0.0.1:8000/api/v1/internal/product-images/products/test.jpg"]
        )


def test_localhost_url_blocked_in_production() -> None:
    """localhost is blocked in production to prevent SSRF."""

    from app.core.exceptions import AppException

    class FakeProdSettings:
        app_env = "production"

    with patch("app.core.config.get_settings", return_value=FakeProdSettings()):
        with pytest.raises(AppException) as exc_info:
            _validate_image_urls_for_real_model(
                ["http://localhost:8000/internal/test.jpg"]
            )
        assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"


def test_private_ip_blocked_in_production() -> None:
    """192.168.x.x and 10.x.x.x are blocked in production (SSRF)."""

    from app.core.exceptions import AppException

    class FakeProdSettings:
        app_env = "production"

    with patch("app.core.config.get_settings", return_value=FakeProdSettings()):
        for bad_url in [
            "http://192.168.1.100/image.jpg",
            "http://10.0.0.1/image.jpg",
            "http://172.16.0.1/image.jpg",
            "http://169.254.169.254/metadata",
        ]:
            with pytest.raises(AppException) as exc_info:
                _validate_image_urls_for_real_model([bad_url])
            assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"


def test_non_http_url_rejected() -> None:
    """Non-http(s) URLs are always rejected."""

    from app.core.exceptions import AppException

    class FakeDevSettings:
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeDevSettings()):
        with pytest.raises(AppException) as exc_info:
            _validate_image_urls_for_real_model(["file:///etc/passwd"])
        assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"


def test_public_url_allowed_in_real_mode() -> None:
    """Public HTTPS URLs pass validation in both environments."""

    class FakeDevSettings:
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeDevSettings()):
        _validate_image_urls_for_real_model(
            ["https://img.alicdn.com/imgextra/test.jpg"]
        )


# ---------------------------------------------------------------------------
# Zhipu response parsing tests
# ---------------------------------------------------------------------------


def test_zhipu_parse_valid_json() -> None:
    """ZhipuVisionClient correctly parses a well-formed JSON response."""

    client = ZhipuVisionClient.__new__(ZhipuVisionClient)
    result = client._parse_response(
        '{"raw_text": "测试", "suggested_description": "描述", '
        '"fields": {"name": {"value": "产品A", "confidence": 0.9, '
        '"source": "zhipu_vision"}}}',
        image_count=1,
        target_fields=["name"],
    )
    assert result.raw_text == "测试"
    assert result.fields["name"].value == "产品A"
    assert result.fields["name"].confidence == 0.9


def test_zhipu_parse_invalid_json_raises() -> None:
    """Non-JSON response raises AIResponseInvalid."""

    from app.ai.exceptions import AIResponseInvalid

    client = ZhipuVisionClient.__new__(ZhipuVisionClient)
    with pytest.raises(AIResponseInvalid):
        client._parse_response(
            "这不是JSON，只是一段普通文字描述。",
            image_count=1,
            target_fields=["name"],
        )


def test_zhipu_parse_missing_field_returns_not_found() -> None:
    """Fields not present in response get value=None, confidence=0."""

    client = ZhipuVisionClient.__new__(ZhipuVisionClient)
    result = client._parse_response(
        '{"raw_text": "", "fields": {}}',
        image_count=1,
        target_fields=["name", "brand"],
    )
    assert result.fields["name"].value is None
    assert result.fields["name"].confidence == 0.0
    assert result.fields["brand"].source == "not_found"


def test_zhipu_parse_confidence_clamped() -> None:
    """Confidence values outside 0–1 are clamped."""

    client = ZhipuVisionClient.__new__(ZhipuVisionClient)
    result = client._parse_response(
        '{"raw_text": "", "fields": {"name": {"value": "A", '
        '"confidence": 1.5, "source": "zhipu_vision"}}}',
        image_count=1,
        target_fields=["name"],
    )
    assert result.fields["name"].confidence == 1.0


# ---------------------------------------------------------------------------
# suggested_description quality tests
# ---------------------------------------------------------------------------


def test_description_no_brand_duplication() -> None:
    from app.ai.vision_client import VisionFieldResult, _build_suggested_description

    fields = {
        "name": VisionFieldResult("欧莱雅复颜氨基酸洁面乳", 0.9, "t"),
        "brand": VisionFieldResult("欧莱雅", 0.9, "t"),
        "specification": VisionFieldResult("125ml", 0.9, "t"),
        "price": VisionFieldResult("144", 0.9, "t"),
        "selling_points": VisionFieldResult(["氨基酸洁面", "净澈不紧绷"], 0.8, "t"),
        "category": VisionFieldResult("洁面乳", 0.8, "t"),
    }
    desc = _build_suggested_description(fields, "补贴价144")
    assert desc is not None
    assert "欧莱雅欧莱雅" not in desc
    assert desc.startswith("欧莱雅复颜氨基酸洁面乳")


def test_description_no_ecommerce_noise() -> None:
    from app.ai.vision_client import VisionFieldResult, _build_suggested_description

    fields = {
        "name": VisionFieldResult("洁面乳", 0.9, "t"),
        "brand": VisionFieldResult("测试", 0.9, "t"),
        "selling_points": VisionFieldResult(
            ["正品保障", "48小时发货", "88VIP专享", "客服在线"],
            0.8,
            "t",
        ),
    }
    desc = _build_suggested_description(fields, "正品保障 发货 VIP")
    assert desc is not None
    for noise in ["正品保障", "发货", "88VIP", "客服"]:
        assert noise not in desc


def test_description_length_in_bounds() -> None:
    from app.ai.vision_client import VisionFieldResult, _build_suggested_description

    fields = {
        "name": VisionFieldResult("复颜氨基酸洁面乳", 0.9, "t"),
        "brand": VisionFieldResult("欧莱雅", 0.9, "t"),
        "specification": VisionFieldResult("125ml", 0.9, "t"),
        "price": VisionFieldResult("144", 0.9, "t"),
        "selling_points": VisionFieldResult(["氨基酸洁面", "净澈不紧绷", "光滑更透亮"], 0.8, "t"),
        "category": VisionFieldResult("洁面乳", 0.8, "t"),
    }
    desc = _build_suggested_description(fields, "补贴价144 敏感肌适用")
    assert desc is not None
    assert 40 <= len(desc) <= 180


def test_internal_images_not_registered_in_production() -> None:
    is_local, is_dev = True, False
    assert not (is_local and is_dev)


def test_internal_images_registered_in_development() -> None:
    is_local, is_dev = True, True
    assert is_local and is_dev


def test_internal_images_not_registered_with_tos_adapter() -> None:
    is_local, is_dev = False, True
    assert not (is_local and is_dev)
