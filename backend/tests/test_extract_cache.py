"""Tests for the extract result in-memory cache."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_extract_cache_hit_skips_vision_call() -> None:
    """Cache hit: vision client NOT called on second identical request."""
    from app.schemas.product import ExtractedFieldValue, ImageExtractRequest, ImageExtractResponse
    from app.services.product_image_extract_service import (
        ProductImageExtractService,
        _cache_put,
        _extract_cache,
        _make_cache_key,
    )

    _extract_cache.clear()
    call_count = 0

    class _CountingClient:
        async def extract_fields(self, *, image_urls, target_fields, locale):
            nonlocal call_count
            call_count += 1
            from app.ai.vision_client import VisionExtractResult

            return VisionExtractResult(raw_text="live", fields={}, source_image_count=1)

    cached_resp = ImageExtractResponse(
        status="ok",
        source_image_count=1,
        raw_text="cached",
        fields={"name": ExtractedFieldValue(value="Cached", confidence=0.9, source="cache")},
        suggested_description="cached desc",
        needs_review=False,
    )

    class FakeSettings:
        image_extract_mode = "vision"
        vision_provider = "mock"
        vision_image_max_side = 720
        vision_image_jpeg_quality = 70
        image_extract_cache_ttl_seconds = 3600
        debug_ai_extract = False

    payload = ImageExtractRequest(
        image_urls=["https://example.com/test_cache_hit.jpg"],
        target_fields=[],
        locale="zh-CN",
    )
    svc = ProductImageExtractService(vision_client=_CountingClient())  # type: ignore[arg-type]

    with patch("app.core.config.get_settings", return_value=FakeSettings()):
        key = await _make_cache_key(payload.image_urls)
        _cache_put(key, cached_resp)
        result = await svc.extract(payload)

    assert call_count == 0, "Vision client must NOT be called on cache hit"
    assert result.raw_text == "cached"


@pytest.mark.asyncio
async def test_extract_cache_disabled_when_ttl_zero() -> None:
    """TTL=0 disables cache; vision client called every time."""
    from app.schemas.product import ImageExtractRequest
    from app.services.product_image_extract_service import (
        ProductImageExtractService,
        _extract_cache,
    )

    _extract_cache.clear()
    call_count = 0

    class _CountingClient:
        async def extract_fields(self, *, image_urls, target_fields, locale):
            nonlocal call_count
            call_count += 1
            from app.ai.vision_client import VisionExtractResult

            return VisionExtractResult(raw_text="", fields={}, source_image_count=1)

    class FakeTTLZeroSettings:
        image_extract_mode = "vision"
        vision_provider = "mock"
        vision_image_max_side = 720
        vision_image_jpeg_quality = 70
        image_extract_cache_ttl_seconds = 0
        debug_ai_extract = False

    svc = ProductImageExtractService(vision_client=_CountingClient())  # type: ignore[arg-type]
    payload = ImageExtractRequest(
        image_urls=["https://example.com/nocache_ttl_zero.jpg"],
        target_fields=[],
        locale="zh-CN",
    )

    with patch("app.core.config.get_settings", return_value=FakeTTLZeroSettings()):
        await svc.extract(payload)
        await svc.extract(payload)

    assert call_count == 2, "Vision client must be called twice when cache TTL=0"
