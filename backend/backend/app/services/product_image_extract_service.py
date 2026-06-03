from __future__ import annotations

import hashlib
import logging
import time

import httpx
from fastapi import status

from app.ai.moderation import SOURCE_VISION_TEXT, LocalModerationAdapter
from app.ai.vision_client import (
    CONFIDENCE_REVIEW_THRESHOLD,
    VisionClientProtocol,
    get_vision_extract_client,
)
from app.core.exceptions import AppException
from app.schemas.product import (
    ExtractedFieldValue,
    ImageExtractRequest,
    ImageExtractResponse,
)

logger = logging.getLogger(__name__)

# Semantic version of the extraction prompt/logic; bump when behaviour changes
# so old cached results are invalidated automatically.
_EXTRACT_PROMPT_VERSION = "v3"

# ---------------------------------------------------------------------------
# In-memory extract cache (dev; swap for Redis in production)
# ---------------------------------------------------------------------------

_extract_cache: dict[str, tuple[float, ImageExtractResponse]] = {}
_CACHE_MAX_SIZE = 100


def _cache_get(key: str, ttl: int) -> ImageExtractResponse | None:
    if ttl <= 0:
        return None
    entry = _extract_cache.get(key)
    if entry is None:
        return None
    ts, resp = entry
    if time.time() - ts > ttl:
        del _extract_cache[key]
        return None
    return resp


def _cache_put(key: str, resp: ImageExtractResponse) -> None:
    if len(_extract_cache) >= _CACHE_MAX_SIZE:
        oldest = min(_extract_cache, key=lambda k: _extract_cache[k][0])
        del _extract_cache[oldest]
    _extract_cache[key] = (time.time(), resp)


async def _compute_image_hash(url: str) -> str:
    """Download image bytes and return SHA-256 hex of raw bytes.

    Falls back to a hash of the URL itself if download fails (e.g. in tests).
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return hashlib.sha256(resp.content).hexdigest()[:32]
    except Exception:
        pass
    return hashlib.sha256(url.encode()).hexdigest()[:32]


async def _make_cache_key(urls: list[str]) -> str:
    """Build a content-based cache key: SHA-256 of image bytes + settings."""
    from app.core.config import get_settings

    s = get_settings()
    # Only hash the first URL (the one actually sent to the model in vision_text mode)
    img_hash = await _compute_image_hash(urls[0]) if urls else "empty"
    raw = "|".join([
        img_hash,
        s.image_extract_mode,
        str(s.vision_image_max_side),
        str(s.vision_image_jpeg_quality),
        _EXTRACT_PROMPT_VERSION,
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ProductImageExtractService:
    """Extract product fields from image URLs using a vision client.

    DB-free — never creates or modifies a Product record.
    """

    def __init__(self, vision_client: VisionClientProtocol | None = None) -> None:
        self._vision_client: VisionClientProtocol = vision_client or get_vision_extract_client()

    async def extract(self, payload: ImageExtractRequest) -> ImageExtractResponse:
        """Run vision extraction and return normalised fields for user review."""

        t0 = time.perf_counter()

        from app.core.config import get_settings
        settings = get_settings()

        # Sanitized diagnostic log (no URLs, no user content)
        logger.info(
            "[extract] mode=%s provider=%s client=%s images=%d max_side=%d",
            settings.image_extract_mode,
            settings.vision_provider,
            type(self._vision_client).__name__,
            len(payload.image_urls),
            settings.vision_image_max_side,
        )

        if not payload.image_urls:
            raise AppException(
                code="IMAGE_URL_NOT_ACCESSIBLE",
                message="image_urls must contain at least one URL",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # --- Cache lookup (content-hash based) ---
        ttl = settings.image_extract_cache_ttl_seconds
        cache_key = await _make_cache_key(payload.image_urls)
        cached = _cache_get(cache_key, ttl)
        if cached is not None:
            logger.info(
                "[extract] cache_hit=true key=%s total_ms=%.0f",
                cache_key, (time.perf_counter() - t0) * 1000,
            )
            return cached

        # --- Vision extraction ---
        t_vision = time.perf_counter()
        raw = await self._vision_client.extract_fields(
            image_urls=payload.image_urls,
            target_fields=payload.target_fields,
            locale=payload.locale,
        )
        vision_ms = (time.perf_counter() - t_vision) * 1000

        normalised: dict[str, ExtractedFieldValue] = {}
        needs_review = False

        for field_name, result in raw.fields.items():
            confidence = max(0.0, min(1.0, float(result.confidence)))
            if confidence < CONFIDENCE_REVIEW_THRESHOLD:
                needs_review = True
            normalised[field_name] = ExtractedFieldValue(
                value=result.value,
                confidence=confidence,
                source=result.source,
            )

        moderation_text = self._join_review_text(
            raw.raw_text,
            raw.suggested_description,
            [field.value for field in normalised.values()],
        )
        moderation_result = await LocalModerationAdapter().review(
            moderation_text,
            source=SOURCE_VISION_TEXT,
        )
        if moderation_result.needs_review:
            needs_review = True

        resp = ImageExtractResponse(
            status="ok",
            source_image_count=raw.source_image_count,
            raw_text=raw.raw_text or None,
            fields=normalised,
            suggested_description=raw.suggested_description,
            needs_review=needs_review,
        )

        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[extract] cache_hit=false vision_ms=%.0f total_ms=%.0f fields=%s",
            vision_ms, total_ms,
            [k for k, v in normalised.items() if v.value is not None],
        )

        # Optional verbose debug log (off by default in production)
        if settings.debug_ai_extract:
            logger.debug(
                "[extract:debug] raw_text_len=%d suggested_desc_len=%d needs_review=%s",
                len(raw.raw_text or ""), len(raw.suggested_description or ""), needs_review,
            )

        # Cache only successful responses
        _cache_put(cache_key, resp)

        return resp

    def _join_review_text(self, *parts: object) -> str:
        flattened: list[str] = []
        for part in parts:
            if part is None:
                continue
            if isinstance(part, list):
                flattened.extend(str(item) for item in part if item is not None)
                continue
            flattened.append(str(part))
        return " ".join(flattened)
