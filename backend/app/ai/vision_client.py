from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from app.ai.exceptions import AIResponseInvalid, AIServiceTimeout, AIServiceUnavailable

logger = logging.getLogger(__name__)

CONFIDENCE_REVIEW_THRESHOLD = 0.8

# ---------------------------------------------------------------------------
# Concurrency protection for the vision path (2-core/2GB box, expo bursts).
# - Semaphore caps in-flight vision requests (bounds provider load + memory).
# - Bounded executor caps concurrent PIL compressions (12MP decode ≈ 36MB each,
#   so this is the real OOM guard) and keeps the event loop unblocked.
# - A waiting-counter rejects requests once the queue is saturated so the
#   process never accumulates work without bound.
# ---------------------------------------------------------------------------
_vision_semaphore: asyncio.Semaphore | None = None
_compress_executor: ThreadPoolExecutor | None = None
_vision_inflight = 0


def _get_vision_semaphore() -> asyncio.Semaphore:
    global _vision_semaphore
    if _vision_semaphore is None:
        from app.core.config import get_settings

        _vision_semaphore = asyncio.Semaphore(get_settings().vision_max_concurrency)
    return _vision_semaphore


def _get_compress_executor() -> ThreadPoolExecutor:
    global _compress_executor
    if _compress_executor is None:
        from app.core.config import get_settings

        _compress_executor = ThreadPoolExecutor(
            max_workers=get_settings().vision_compress_workers,
            thread_name_prefix="vision-compress",
        )
    return _compress_executor


class _VisionConcurrencyGuard:
    """Bound concurrent vision work; fast-reject once the queue is saturated."""

    async def __aenter__(self) -> "_VisionConcurrencyGuard":
        global _vision_inflight
        from app.core.config import get_settings

        settings = get_settings()
        cap = settings.vision_max_concurrency + settings.vision_max_queue
        if _vision_inflight >= cap:
            logger.warning("vision_overloaded inflight=%d cap=%d", _vision_inflight, cap)
            from fastapi import status as http_status

            from app.core.exceptions import AppException

            raise AppException(
                code="VISION_BUSY",
                message="识别服务繁忙，请稍后重试",
                http_status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        _vision_inflight += 1
        try:
            await _get_vision_semaphore().acquire()
        except BaseException:
            _vision_inflight -= 1
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        global _vision_inflight
        _get_vision_semaphore().release()
        _vision_inflight -= 1

ALL_KNOWN_FIELDS = [
    "name",
    "brand",
    "category",
    "price",
    "specification",
    "ingredients",
    "selling_points",
    "usage_scenario",
    "claims",
    "appearance",
]

import ipaddress
import re as _re

# Always-blocked patterns (mock domains, unroutable)
_ALWAYS_BLOCKED = (
    "mock-cdn.local",
    "mock-tos.local",
    "0.0.0.0",
)

# Private/loopback CIDR ranges blocked in production
_PRIVATE_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / IMDS
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_PRIVATE_HOST_PATTERNS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",  # AWS/GCP IMDS
)


def _is_private_host(host: str) -> bool:
    """Return True if host resolves to a private/loopback address.

    For hostnames (non-IP literals), performs DNS resolution and checks ALL
    returned addresses against private CIDR ranges. This prevents DNS
    rebinding attacks where an attacker-controlled domain resolves to an
    internal IP (e.g. 169.254.169.254 for cloud IMDS).
    """
    import socket

    if host.lower() in _PRIVATE_HOST_PATTERNS:
        return True
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_CIDRS)
    except ValueError:
        # Not an IP literal — resolve hostname and check ALL A/AAAA records.
        try:
            addrinfos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            for family, _type, _proto, _canonname, sockaddr in addrinfos:
                ip_str = sockaddr[0]
                try:
                    addr = ipaddress.ip_address(ip_str)
                    if any(addr in net for net in _PRIVATE_CIDRS):
                        return True
                except ValueError:
                    continue
        except socket.gaierror:
            # DNS resolution failed — treat as private (fail-closed)
            return True
        return False


def _validate_image_urls_for_real_model(image_urls: list[str]) -> None:
    """Reject fake, non-HTTP, or (in production) private-network image URLs.

    In development+local mode: only mock domains are blocked so localhost
    works for the internal storage endpoint.
    In production: additionally blocks all private/loopback IPs.
    """
    import urllib.parse

    from fastapi import status as http_status

    from app.core.config import get_settings
    from app.core.exceptions import AppException

    settings = get_settings()
    is_production = settings.app_env.strip().lower() == "production"

    for url in image_urls:
        # Must be http or https
        if not url.lower().startswith(("http://", "https://")):
            raise AppException(
                code="IMAGE_URL_NOT_ACCESSIBLE",
                message=f"图片 URL 必须以 http:// 或 https:// 开头: {url[:120]}",
                http_status=http_status.HTTP_400_BAD_REQUEST,
            )

        # Always-blocked patterns
        for pattern in _ALWAYS_BLOCKED:
            if pattern in url:
                raise AppException(
                    code="IMAGE_URL_NOT_ACCESSIBLE",
                    message=f"图片 URL 不可访问: {url[:120]}",
                    http_status=http_status.HTTP_400_BAD_REQUEST,
                )

        # Production: block private/internal network access (SSRF protection)
        if is_production:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ""
            if _is_private_host(host):
                raise AppException(
                    code="IMAGE_URL_NOT_ACCESSIBLE",
                    message=(
                        f"生产环境不允许访问内网地址: {url[:120]}。"
                        "请使用公网可访问的图片 URL。"
                    ),
                    http_status=http_status.HTTP_400_BAD_REQUEST,
                )


def _compress_image_for_vision(img_bytes: bytes, content_type: str) -> bytes:
    """Resize and re-encode an image so it stays small for vision models.

    Uses VISION_IMAGE_MAX_SIDE / VISION_IMAGE_JPEG_QUALITY from settings.
    If the compressed version is not smaller, return the original.
    """

    try:
        from PIL import Image
    except ImportError:
        return img_bytes

    from app.core.config import get_settings

    settings = get_settings()
    max_side = settings.vision_image_max_side
    quality = settings.vision_image_jpeg_quality

    import io

    try:
        img = Image.open(io.BytesIO(img_bytes))
    except Exception:
        return img_bytes

    w, h = img.size
    long_edge = max(w, h)

    if long_edge <= max_side and len(img_bytes) < 200 * 1024:
        return img_bytes

    if long_edge > max_side:
        scale = max_side / long_edge
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    compressed = buf.getvalue()

    if len(compressed) < len(img_bytes):
        return compressed
    return img_bytes


# Category → friendly Chinese label for description
_CATEGORY_LABELS: dict[str, str] = {
    "洁面": "洁面产品", "洗面奶": "洁面产品", "洁面乳": "洁面产品",
    "面霜": "面霜产品", "乳液": "乳液产品", "精华": "精华产品",
    "眼霜": "眼部护理产品", "eye cream": "眼部护理产品",
    "面膜": "面膜产品", "防晒": "防晒产品", "卸妆": "卸妆产品",
    "护肤品": "护肤产品", "skincare": "护肤产品",
    "彩妆": "彩妆产品", "makeup": "彩妆产品",
    "洗发": "洗护产品", "沐浴": "个护产品", "身体": "身体护理产品",
}

# Noise words to strip from selling points and description
_SP_NOISE = (
    "发货", "客服", "购物车", "加购", "VIP", "消费券", "优惠券",
    "包邮", "退货", "退款", "运费", "赠品", "分期", "售后",
    "正品保障", "官方正品", "旗舰店", "88VIP", "信用卡",
)


def _build_suggested_description(
    fields: dict[str, "VisionFieldResult"],
    raw_text: str,
) -> str | None:
    """Build a 100-180 char product research description from extracted fields.

    No LLM call — pure string assembly.
    """

    def _v(key: str) -> str | None:
        f = fields.get(key)
        if f and f.value and f.confidence > 0.3:
            return str(f.value) if not isinstance(f.value, list) else None
        return None

    def _vlist(key: str) -> list[str]:
        f = fields.get(key)
        if f and isinstance(f.value, list) and f.confidence > 0.3:
            return [str(s) for s in f.value if s]
        return []

    brand = _v("brand")
    name = _v("name")
    category = _v("category")
    spec = _v("specification")
    price = _v("price")
    selling_points = _vlist("selling_points")

    # Filter noise from selling points
    clean_sp = [
        sp for sp in selling_points
        if not any(n in sp for n in _SP_NOISE)
    ][:4]

    # Resolve category label
    cat_label = ""
    if category:
        low = category.lower()
        for pat, label in _CATEGORY_LABELS.items():
            if pat in low:
                cat_label = label
                break
        if not cat_label:
            cat_label = f"{category}产品"

    # --- Sentence 1: 品牌 + 产品名 + 规格 + 价格 + 类目 ---
    s1_parts: list[str] = []

    # Deduplicate: if name already starts with brand, don't prepend brand
    title = ""
    if brand and name:
        if name.startswith(brand):
            title = name
        else:
            title = f"{brand}{name}"
    elif name:
        title = name
    elif brand:
        title = f"{brand}产品"

    if title:
        s1_parts.append(title)
    if spec:
        s1_parts.append(f"规格{spec}")
    if price:
        price_label = "售价约"
        raw_lower = (raw_text or "").lower()
        for kw, lbl in [("补贴", "补贴价约"), ("券后", "券后价约"), ("到手", "到手价约"),
                         ("促销", "促销价约"), ("活动", "活动价约")]:
            if kw in raw_lower:
                price_label = lbl
                break
        s1_parts.append(f"{price_label}{price}元")
    if cat_label:
        s1_parts.append(f"属于{cat_label}")

    sentence1 = "，".join(s1_parts) + "。" if s1_parts else ""

    # --- Sentence 2: 核心卖点 + 皮肤类型提示 ---
    sentence2 = ""
    skin_hints: list[str] = []
    if raw_text:
        for kw in ["敏感肌适用", "敏感肌", "油性肌", "干性肌", "混合肌", "所有肤质", "全肤质"]:
            if kw in raw_text:
                skin_hints.append(kw)
                break

    if clean_sp:
        joined = "、".join(clean_sp)
        sentence2 = f"产品主打{joined}"
        if skin_hints:
            sentence2 += f"，标注{skin_hints[0]}"
        sentence2 += "。"

    # --- Sentence 3: 补充功效关键词（仅在卖点中有明确功效词时才添加） ---
    sentence3 = ""
    _EFFICACY_KEYWORDS = {
        "保湿": "保湿补水", "补水": "保湿补水", "锁水": "保湿补水",
        "修护": "修护舒缓", "修复": "修护舒缓", "舒缓": "修护舒缓",
        "抗皱": "抗皱紧致", "淡纹": "抗皱紧致", "紧致": "抗皱紧致",
        "控油": "控油清爽", "清爽": "控油清爽",
        "美白": "美白提亮", "透亮": "清透亮肤感", "焕亮": "清透亮肤感",
        "光滑": "肌肤柔滑细腻",
    }
    efficacy_found: list[str] = []
    seen_eff: set[str] = set()
    for sp in clean_sp[:4]:
        for kw, label in _EFFICACY_KEYWORDS.items():
            if kw in sp and label not in seen_eff:
                efficacy_found.append(label)
                seen_eff.add(label)
                break
    # Only add sentence 3 if it provides info beyond the raw selling points
    if efficacy_found and len(efficacy_found) >= 2:
        sentence3 = f"功效聚焦于{'、'.join(efficacy_found)}。"

    # --- Sentence 4: 适合的调研场景和目标人群 ---
    sentence4 = ""
    scenarios: list[str] = []
    audience: list[str] = []

    if cat_label:
        if "洁面" in cat_label:
            scenarios.append("日常洁面")
        elif "面霜" in cat_label or "乳液" in cat_label:
            scenarios.append("日常保湿护理")
        elif "精华" in cat_label:
            scenarios.append("密集修护场景")
        elif "防晒" in cat_label:
            scenarios.append("日常防晒场景")
        elif "眼" in cat_label:
            scenarios.append("眼部护理场景")
        else:
            scenarios.append("日常护理场景")

    if any("温和" in sp or "敏感" in sp for sp in clean_sp) or "敏感肌" in (raw_text or ""):
        audience.append("敏感肌用户")
    if any("控油" in sp or "清爽" in sp for sp in clean_sp):
        audience.append("油性肌用户")
    if any("抗皱" in sp or "淡纹" in sp or "紧致" in sp for sp in clean_sp):
        audience.append("抗老需求用户")
    if not audience:
        audience.append("目标消费者")

    combined = scenarios + [f"{'和'.join(audience)}调研"]
    sentence4 = f"适合用于{'、'.join(combined)}。"

    desc = sentence1 + sentence2 + sentence3 + sentence4

    if not desc:
        # Absolute fallback: use truncated raw_text
        if raw_text and len(raw_text.strip()) > 10:
            return raw_text.strip()[:180]
        return None

    # Trim to 180 chars max
    if len(desc) > 180:
        desc = desc[:177] + "…。"

    return desc


@dataclass
class VisionFieldResult:
    """Single field extracted from images."""

    value: Any
    confidence: float
    source: str


@dataclass
class VisionExtractResult:
    """Raw output from a vision extraction call."""

    raw_text: str | None
    fields: dict[str, VisionFieldResult]
    suggested_description: str | None = None
    source_image_count: int = 0


@runtime_checkable
class VisionClientProtocol(Protocol):
    """Protocol for pluggable vision extraction backends."""

    async def extract_fields(
        self,
        *,
        image_urls: list[str],
        target_fields: list[str],
        locale: str,
    ) -> VisionExtractResult: ...


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------


class MockVisionClient:
    """Stable mock that returns deterministic fake data for frontend integration."""

    async def extract_fields(
        self,
        *,
        image_urls: list[str],
        target_fields: list[str],
        locale: str,
    ) -> VisionExtractResult:
        """Return mock product fields suitable for frontend dev/test."""

        effective_fields = target_fields if target_fields else ALL_KNOWN_FIELDS

        all_mock: dict[str, VisionFieldResult] = {
            "name": VisionFieldResult(value="焕颜修护精华面霜", confidence=0.92, source="image_ocr"),
            "brand": VisionFieldResult(value="测试品牌", confidence=0.88, source="image_ocr"),
            "category": VisionFieldResult(value="护肤品", confidence=0.75, source="llm_inference"),
            "price": VisionFieldResult(value="199", confidence=0.70, source="image_ocr"),
            "specification": VisionFieldResult(value="50ml", confidence=0.85, source="image_ocr"),
            "ingredients": VisionFieldResult(
                value=["烟酰胺", "神经酰胺", "玻尿酸"],
                confidence=0.78,
                source="vision_llm",
            ),
            "selling_points": VisionFieldResult(
                value=["温和修护", "长效保湿", "提亮肤色"],
                confidence=0.72,
                source="vision_llm",
            ),
            "usage_scenario": VisionFieldResult(value="日常护肤", confidence=0.68, source="llm_inference"),
            "claims": VisionFieldResult(
                value=["经皮肤科测试", "适合敏感肌"],
                confidence=0.65,
                source="vision_llm",
            ),
        }

        extracted: dict[str, VisionFieldResult] = {}
        for f in effective_fields:
            if f in all_mock:
                extracted[f] = all_mock[f]
            else:
                extracted[f] = VisionFieldResult(value=None, confidence=0.0, source="not_found")

        return VisionExtractResult(
            raw_text="焕颜修护精华面霜 50ml 烟酰胺+神经酰胺 温和修护 适合敏感肌 建议零售价¥199",
            fields=extracted,
            suggested_description="一款主打温和修护和提亮功效的面霜，含烟酰胺与神经酰胺核心成分，适合敏感肌日常使用。",
            source_image_count=len(image_urls),
        )


# ---------------------------------------------------------------------------
# Zhipu GLM-4V (real vision model)
# ---------------------------------------------------------------------------


class ZhipuVisionClient:
    """Call Zhipu GLM-4V via non-streaming OpenAI-compatible HTTP call.

    GLM-4V does not support ``stream: true`` when images are present
    (error 1210 "图片输入格式/解析错误"), so we use a direct httpx POST
    instead of the project's ArkOpenAIClient (which forces streaming).
    """

    _REQUEST_TIMEOUT = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def extract_fields(
        self,
        *,
        image_urls: list[str],
        target_fields: list[str],
        locale: str,
    ) -> VisionExtractResult:
        """Send images to Zhipu GLM and parse structured JSON response."""

        t_total = time.perf_counter()
        logger.info("[vision] client=ZhipuVisionClient images=%d", len(image_urls))
        _validate_image_urls_for_real_model(image_urls)

        effective_fields = target_fields if target_fields else ALL_KNOWN_FIELDS

        from app.ai.prompts.product_image_extract import render_prompt

        system_prompt = render_prompt(target_fields=effective_fields, locale=locale)

        # System prompt already specifies the full flat JSON schema; keep the
        # user turn short so smaller/faster models (e.g. doubao mini) don't get
        # overloaded by duplicated instructions and return blank fields.
        user_prompt = "请分析图片中的产品，按系统要求的扁平 JSON 格式提取信息。"

        from app.core.config import get_settings

        max_attempts = max(1, get_settings().vision_max_retries + 1)
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                raw_response = await self._call_zhipu(
                    system=system_prompt,
                    user=user_prompt,
                    image_urls=image_urls,
                )
                result = self._parse_response(
                    raw_response, len(image_urls), effective_fields
                )
            except AIServiceUnavailable as exc:
                # Overload fast-reject (VISION_BUSY) is an AppException, not this —
                # so this branch is a genuine provider/network failure: retry.
                last_exc = exc
                logger.warning(
                    "vision_extract_attempt_failed attempt=%d/%d err=%s",
                    attempt + 1, max_attempts, exc,
                )
                continue
            except (AIResponseInvalid, AIServiceTimeout) as exc:
                last_exc = exc
                logger.warning(
                    "vision_extract_attempt_failed attempt=%d/%d err=%s",
                    attempt + 1, max_attempts, exc,
                )
                continue

            # Blank-paper guard: a structurally-valid response with no product
            # name means the model "gave up" — retry rather than return junk.
            name_fr = result.fields.get("name")
            blank = name_fr is None or name_fr.value in (None, "", [])
            if blank and attempt < max_attempts - 1:
                logger.warning(
                    "vision_extract_blank attempt=%d/%d, retrying",
                    attempt + 1, max_attempts,
                )
                continue

            logger.info(
                "[perf] zhipu extract_fields total=%.1fms images=%d attempt=%d",
                (time.perf_counter() - t_total) * 1000, len(image_urls), attempt + 1,
            )
            return result

        # All attempts failed — surface the last error so the caller can fall
        # back (frontend shows manual-fill prompt).
        raise last_exc or AIResponseInvalid("视觉提取多次失败")

    async def _call_zhipu(
        self,
        *,
        system: str,
        user: str,
        image_urls: list[str],
    ) -> str:
        """Concurrency-guarded entry point for one vision API call."""

        async with _VisionConcurrencyGuard():
            return await self._call_zhipu_impl(
                system=system, user=user, image_urls=image_urls
            )

    async def _call_zhipu_impl(
        self,
        *,
        system: str,
        user: str,
        image_urls: list[str],
    ) -> str:
        """Non-streaming OpenAI-compatible chat completion with images.

        Zhipu GLM-4V has strict URL access restrictions — most external CDNs
        trigger error 1210. To work reliably, we download each image and pass
        it as base64 data-URL, which is always accepted.
        """

        import base64 as _b64

        import httpx as _httpx

        # Download images and convert to base64 data-URLs
        t_dl_total = time.perf_counter()
        base64_images: list[str] = []
        # follow_redirects=False: prevent redirect-based SSRF bypass.
        # All URLs have already been validated by _validate_image_urls_for_real_model;
        # disabling redirects ensures an attacker cannot use a 302 to reach internal IPs.
        async with _httpx.AsyncClient(
            timeout=_httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0),
            follow_redirects=False,
        ) as dl_client:
            for idx, img_url in enumerate(image_urls):
                t_dl = time.perf_counter()
                try:
                    resp = await dl_client.get(img_url)
                    if resp.status_code != 200:
                        logger.warning(
                            "zhipu_image_download_failed url=%s status=%d",
                            img_url[:120],
                            resp.status_code,
                        )
                        raise AIServiceUnavailable(
                            f"图片下载失败 (HTTP {resp.status_code}): {img_url[:120]}"
                        )
                except _httpx.TimeoutException as exc:
                    raise AIServiceTimeout(f"图片下载超时: {img_url[:120]}") from exc
                except AIServiceUnavailable:
                    raise
                except AIServiceTimeout:
                    raise
                except Exception as exc:
                    raise AIServiceUnavailable(
                        f"图片下载失败: {img_url[:120]} — {str(exc)[:100]}"
                    ) from exc

                dl_ms = (time.perf_counter() - t_dl) * 1000
                ct = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                if ct not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                    ct = "image/jpeg"

                # Compress large images before sending to vision model.
                # Offload to a bounded thread pool: PIL decode of a 12MP photo
                # holds ~36MB, so capping concurrent compressions is the OOM
                # guard, and it keeps the single event loop unblocked.
                t_compress = time.perf_counter()
                img_bytes = resp.content
                original_kb = len(img_bytes) // 1024
                img_bytes = await asyncio.get_event_loop().run_in_executor(
                    _get_compress_executor(), _compress_image_for_vision, img_bytes, ct
                )
                compressed_kb = len(img_bytes) // 1024
                compress_ms = (time.perf_counter() - t_compress) * 1000
                # After compression, always JPEG
                if compressed_kb < original_kb:
                    ct = "image/jpeg"

                t_b64 = time.perf_counter()
                b64 = _b64.b64encode(img_bytes).decode()
                b64_ms = (time.perf_counter() - t_b64) * 1000
                base64_images.append(f"data:{ct};base64,{b64}")
                logger.info(
                    "[perf] image[%d] download=%.1fms compress=%.1fms (%dKB->%dKB) base64=%.1fms",
                    idx, dl_ms, compress_ms, original_kb, compressed_kb, b64_ms,
                )

        logger.info("[perf] all images download+base64 total=%.1fms", (time.perf_counter() - t_dl_total) * 1000)

        # Build messages with base64 images
        from app.ai.client import ArkOpenAIClient

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        messages = ArkOpenAIClient._build_messages(system, user, base64_images)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        # 图片字段提取是 OCR 型任务，关掉 glm-4.6v 的自动思考并给输出封顶，
        # 砍掉隐藏推理 token 与长尾延迟。.env 可单独回滚（见 config）。
        from app.core.config import get_settings

        _vs = get_settings()
        if _vs.vision_disable_thinking:
            payload["thinking"] = {"type": "disabled"}
            # 仅在关思考时封顶：没有推理 token 占预算，cap 纯粹用于截断长尾。
            # 开思考回滚时绝不加 cap，否则推理会吃光预算导致正文空 content。
            if _vs.vision_max_tokens:
                payload["max_tokens"] = _vs.vision_max_tokens

        t_api = time.perf_counter()
        try:
            async with _httpx.AsyncClient(timeout=self._REQUEST_TIMEOUT) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except _httpx.TimeoutException as exc:
            logger.info("[perf] zhipu API call=%.1fms TIMEOUT", (time.perf_counter() - t_api) * 1000)
            raise AIServiceTimeout(f"智谱视觉模型请求超时: {exc}") from exc
        except Exception as exc:
            logger.info("[perf] zhipu API call=%.1fms ERROR", (time.perf_counter() - t_api) * 1000)
            logger.exception("zhipu_vision_http_failed")
            raise AIServiceUnavailable(
                f"智谱视觉模型网络错误: {str(exc)[:200]}"
            ) from exc

        logger.info("[perf] zhipu API call=%.1fms status=%d", (time.perf_counter() - t_api) * 1000, resp.status_code)

        if resp.status_code != 200:
            body = resp.text[:500]
            logger.error("zhipu_vision_api_error status=%d body=%s", resp.status_code, body)
            if resp.status_code == 429:
                from app.ai.exceptions import AIRateLimited

                raise AIRateLimited(f"智谱 API 限流: {body}")
            raise AIServiceUnavailable(
                f"智谱视觉模型返回 {resp.status_code}: {body[:200]}"
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise AIResponseInvalid("智谱返回空 choices")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise AIResponseInvalid("智谱返回空 content")
        return content

    def _parse_response(
        self,
        raw_response: str,
        image_count: int,
        target_fields: list[str],
    ) -> VisionExtractResult:
        """Parse Zhipu's JSON response into VisionExtractResult."""

        from app.ai.json_utils import extract_json_object

        try:
            json_str = extract_json_object(raw_response)
            data = json.loads(json_str)
        except (AIResponseInvalid, json.JSONDecodeError) as exc:
            logger.error("zhipu_vision_json_parse_failed raw=%s", raw_response[:500])
            raise AIResponseInvalid(
                f"智谱返回内容无法解析为 JSON: {str(exc)[:200]}"
            ) from exc

        if not isinstance(data, dict):
            raise AIResponseInvalid(f"Expected JSON object, got {type(data).__name__}")

        raw_text = data.get("raw_text")
        suggested_description = data.get("suggested_description")
        fields_data = data.get("fields", {})
        if not isinstance(fields_data, dict):
            fields_data = {}

        fields: dict[str, VisionFieldResult] = {}
        for field_name in target_fields:
            fd = fields_data.get(field_name)
            if isinstance(fd, dict) and "value" in fd:
                # Legacy nested format: {"value":..,"confidence":..,"source":..}
                value = fd.get("value")
                confidence = max(0.0, min(1.0, float(fd.get("confidence", 0.0))))
                source = str(fd.get("source", "vision"))
            else:
                # Flat format (current schema): field value at top level.
                # Confidence is synthesized — present=1.0, missing=0.0.
                value = data.get(field_name)
                confidence = 1.0
                source = "vision"
            if value in (None, "", [], "null", "NULL"):
                fields[field_name] = VisionFieldResult(
                    value=None, confidence=0.0, source="not_found",
                )
            else:
                fields[field_name] = VisionFieldResult(
                    value=value, confidence=confidence, source=source,
                )

        return VisionExtractResult(
            raw_text=str(raw_text) if raw_text else None,
            fields=fields,
            suggested_description=str(suggested_description) if suggested_description else None,
            source_image_count=image_count,
        )


# ---------------------------------------------------------------------------
# Zhipu Vision-Text two-step mode
# ---------------------------------------------------------------------------


class ZhipuVisionTextClient:
    """Two-step extraction: Zhipu GLM-4V for OCR, then DeepSeek for structuring.

    Step 1: GLM-4V reads all visible text from images (raw_text only).
    Step 2: DeepSeek parses raw_text into structured fields + description.

    This is faster than single-step ``ZhipuVisionClient`` because the vision
    model only needs to output plain text (shorter output, simpler task),
    and the text structuring is handled by a fast text model.
    """

    def __init__(self, zhipu_client: ZhipuVisionClient) -> None:
        self._zhipu = zhipu_client

    async def extract_fields(
        self,
        *,
        image_urls: list[str],
        target_fields: list[str],
        locale: str,
    ) -> VisionExtractResult:
        _MIN_USEFUL_TEXT_LEN = 20

        t_total = time.perf_counter()
        logger.info("[vision_text] client=ZhipuVisionTextClient images=%d", len(image_urls))
        _validate_image_urls_for_real_model(image_urls)

        effective_fields = target_fields if target_fields else ALL_KNOWN_FIELDS

        # --- Step 1: Vision OCR (Zhipu GLM-4V) ---
        # Only send the first image; add 2nd only if raw_text is too short.
        t_ocr = time.perf_counter()
        first_urls = image_urls[:1]
        raw_text = await self._ocr_raw_text(first_urls)
        ocr_ms = (time.perf_counter() - t_ocr) * 1000
        logger.info("[perf] vision_text step1_ocr=%.1fms raw_text_len=%d (1st image)", ocr_ms, len(raw_text.strip()))

        if len(raw_text.strip()) < _MIN_USEFUL_TEXT_LEN and len(image_urls) > 1:
            logger.info("[perf] raw_text too short (%d chars), adding 2nd image", len(raw_text.strip()))
            t_ocr2 = time.perf_counter()
            raw_text_2 = await self._ocr_raw_text(image_urls[1:2])
            ocr2_ms = (time.perf_counter() - t_ocr2) * 1000
            logger.info("[perf] vision_text step1_ocr_2nd=%.1fms raw_text_len=%d", ocr2_ms, len(raw_text_2.strip()))
            raw_text = raw_text.strip() + "\n\n" + raw_text_2.strip()

        if not raw_text.strip():
            # No text found in images — return empty fields
            fields = {f: VisionFieldResult(value=None, confidence=0.0, source="not_found") for f in effective_fields}
            return VisionExtractResult(
                raw_text=None, fields=fields, source_image_count=len(image_urls),
            )

        # --- Step 2: Text structuring (DeepSeek) ---
        t_struct = time.perf_counter()
        result = await self._structure_fields(raw_text, effective_fields, locale, len(image_urls))
        struct_ms = (time.perf_counter() - t_struct) * 1000

        # --- Step 2b: If name/brand missing and 2nd image available, try it ---
        name_found = result.fields.get("name") and result.fields["name"].value
        brand_found = result.fields.get("brand") and result.fields["brand"].value
        if not name_found and not brand_found and len(image_urls) > 1:
            logger.info("[perf] name+brand missing after 1st image, trying 2nd image")
            t_ocr2 = time.perf_counter()
            raw_text_2 = await self._ocr_raw_text(image_urls[1:2])
            ocr2_ms = (time.perf_counter() - t_ocr2) * 1000
            logger.info("[perf] vision_text step1_ocr_2nd=%.1fms raw_text_len=%d", ocr2_ms, len(raw_text_2.strip()))
            if raw_text_2.strip():
                combined = raw_text.strip() + "\n\n" + raw_text_2.strip()
                t_struct2 = time.perf_counter()
                result = await self._structure_fields(combined, effective_fields, locale, len(image_urls))
                struct2_ms = (time.perf_counter() - t_struct2) * 1000
                struct_ms += ocr2_ms + struct2_ms

        total_ms = (time.perf_counter() - t_total) * 1000
        logger.info(
            "[perf] vision_text step2_structure=%.1fms total=%.1fms images=%d",
            struct_ms, total_ms, len(image_urls),
        )
        return result

    async def _ocr_raw_text(self, image_urls: list[str]) -> str:
        """Call Zhipu GLM-4V with a minimal OCR-only prompt."""

        system = (
            "你是一个图片文字抄写员。只做一件事：把图片上所有可见文字原样抄写下来。\n"
            "规则：\n"
            "- 只输出纯文本，不输出 JSON\n"
            "- 不分析、不总结、不推理\n"
            "- 保留所有价格、规格、品牌名、产品名、功效词、成分词\n"
            "- 保留原始排版顺序\n"
            "- 多张图片用 [图片1] [图片2] 标记分隔\n"
            '- 如果图片上没有文字，输出"无可见文字"'
        )
        user = "请抄写图片中所有可见文字。"

        return await self._zhipu._call_zhipu(
            system=system,
            user=user,
            image_urls=image_urls,
        )

    # ------------------------------------------------------------------
    # Step 2 helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_extract(raw_text: str) -> dict[str, str | None]:
        """Fast regex pre-extraction for price and specification."""

        import re

        hints: dict[str, str | None] = {"price": None, "specification": None}

        # Price: prefer 券后价/到手价/促销价, then ¥/￥ numbers
        for pat in [
            r"(?:券后|到手|促销|活动)[价價]?\s*[:：]?\s*[¥￥]?\s*(\d+(?:\.\d+)?)",
            r"[¥￥]\s*(\d+(?:\.\d+)?)",
            r"(?:价格|售价|零售价|标价)\s*[:：]?\s*[¥￥]?\s*(\d+(?:\.\d+)?)",
            r"[Pp]rice\s*[:：]?\s*[¥￥]?\s*(\d+(?:\.\d+)?)",
        ]:
            m = re.search(pat, raw_text)
            if m:
                hints["price"] = m.group(1)
                break

        # Specification: ml/g/片/粒/支/包
        m = re.search(r"(\d+(?:\.\d+)?\s*(?:ml|ML|mL|g|kg|KG|片|粒|支|包|袋|瓶|盒|条|张))", raw_text)
        if m:
            hints["specification"] = m.group(1)

        return hints

    async def _structure_fields(
        self,
        raw_text: str,
        target_fields: list[str],
        locale: str,
        image_count: int,
    ) -> VisionExtractResult:
        """Call DeepSeek to structure raw_text into product fields.

        Optimised for speed: slim prompt, no description generation,
        local rule hints for price/spec, max 3 selling points.
        """

        # --- Local rule pre-extraction ---
        t_rule = time.perf_counter()
        hints = self._rule_extract(raw_text)
        rule_ms = (time.perf_counter() - t_rule) * 1000
        logger.info("[perf] rule_extract=%.1fms hints=%s", rule_ms, hints)

        from app.ai.factory import get_ai_client

        ai_client = get_ai_client()

        # Only ask DeepSeek for the core fields
        _CORE_FIELDS = ["name", "brand", "category", "price", "specification", "selling_points"]
        ask_fields = [f for f in target_fields if f in _CORE_FIELDS]
        # Fields not asked from DeepSeek get null
        skip_fields = [f for f in target_fields if f not in _CORE_FIELDS]

        fields_list = ", ".join(f'"{f}"' for f in ask_fields)

        hint_lines = ""
        if hints["price"]:
            hint_lines += f'本地规则已提取到价格: {hints["price"]}，请校验。\n'
        if hints["specification"]:
            hint_lines += f'本地规则已提取到规格: {hints["specification"]}，请校验。\n'

        system = (
            "从OCR文字提取产品信息。只输出JSON，不输出其他文字。\n"
            "格式示例：\n"
            '{"fields":{"name":{"value":"产品名","confidence":0.9,"source":"text_extraction"},'
            '"brand":{"value":"品牌名","confidence":0.9,"source":"text_extraction"},'
            '"selling_points":{"value":["卖点1","卖点2"],"confidence":0.8,"source":"text_extraction"}}}\n'
            "规则：selling_points最多3条数组。没有的字段value填null、confidence填0。不编造。"
        )

        user = (
            f"{hint_lines}"
            f"OCR文字：\n{raw_text}\n\n"
            f"请提取这些字段：{fields_list}"
        )

        prompt_len = len(system) + len(user)

        from app.core.config import get_settings
        settings = get_settings()
        endpoint_id = settings.deepseek_model_flash

        t_ds = time.perf_counter()
        response_text = await ai_client.complete_json(
            system=system,
            user=user,
            endpoint_id=endpoint_id,
            max_tokens=512,
        )
        ds_ms = (time.perf_counter() - t_ds) * 1000
        logger.info("[perf] deepseek structuring=%.1fms prompt_len=%d response_len=%d", ds_ms, prompt_len, len(response_text))
        from app.core.config import get_settings as _gs
        if _gs().debug_ai_extract:
            logger.debug("[debug] deepseek raw response: %s", response_text[:800])

        # Parse DeepSeek JSON response
        from app.ai.json_utils import extract_json_object

        try:
            json_str = extract_json_object(response_text)
            data = json.loads(json_str)
        except (AIResponseInvalid, json.JSONDecodeError) as exc:
            logger.error("vision_text_json_parse_failed raw=%s", response_text[:500])
            raise AIResponseInvalid(
                f"文本结构化返回无法解析为 JSON: {str(exc)[:200]}"
            ) from exc

        if not isinstance(data, dict):
            raise AIResponseInvalid(f"Expected JSON object, got {type(data).__name__}")

        fields_data = data.get("fields", {})

        fields: dict[str, VisionFieldResult] = {}
        for field_name in ask_fields:
            fd = fields_data.get(field_name)
            if fd and isinstance(fd, dict):
                value = fd.get("value")
                # Truncate selling_points to max 3
                if field_name == "selling_points" and isinstance(value, list):
                    value = value[:3]
                confidence = float(fd.get("confidence", 0.0))
                confidence = max(0.0, min(1.0, confidence))
                source = str(fd.get("source", "text_extraction"))
                fields[field_name] = VisionFieldResult(
                    value=value, confidence=confidence, source=source,
                )
            else:
                # Fall back to local rule hint if available
                rule_val = hints.get(field_name)
                if rule_val:
                    fields[field_name] = VisionFieldResult(
                        value=rule_val, confidence=0.6, source="rule_extract",
                    )
                else:
                    fields[field_name] = VisionFieldResult(
                        value=None, confidence=0.0, source="not_found",
                    )

        # Fill skipped fields with nulls
        for field_name in skip_fields:
            fields[field_name] = VisionFieldResult(
                value=None, confidence=0.0, source="not_found",
            )

        # Generate 100-180 char product research description (no LLM call)
        suggested = _build_suggested_description(fields, raw_text)

        return VisionExtractResult(
            raw_text=raw_text,
            fields=fields,
            suggested_description=suggested,
            source_image_count=image_count,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_vision_extract_client() -> VisionClientProtocol:
    """Return the appropriate VisionClient based on VISION_PROVIDER / AI_PROVIDER.

    Resolution order:
    1. VISION_PROVIDER if explicitly set (``mock`` or ``zhipu``)
    2. Fall back to AI_PROVIDER (``mock`` → MockVisionClient, else check zhipu key)
    """

    from app.core.config import get_settings

    settings = get_settings()
    provider = settings.vision_provider.strip().lower()

    # If VISION_PROVIDER not set, inherit from AI_PROVIDER
    if not provider:
        provider = settings.ai_provider.strip().lower()
        # When AI_PROVIDER is "deepseek" and zhipu key exists, auto-select zhipu
        if provider != "mock" and settings.zhipu_api_key:
            provider = "zhipu"

    if provider == "mock":
        return MockVisionClient()

    if provider in ("zhipu", "doubao"):
        # ZhipuVisionClient is a generic OpenAI-compatible vision client; for
        # doubao we just feed it Ark credentials + the doubao model. Both honor
        # vision_disable_thinking / vision_max_tokens in _call_zhipu.
        if provider == "doubao":
            if not settings.ark_api_key:
                raise AIServiceUnavailable(
                    "VISION_PROVIDER=doubao 需要配置 ARK_API_KEY 环境变量。"
                )
            client = ZhipuVisionClient(
                api_key=settings.ark_api_key,
                base_url=settings.ark_base_url,
                model=settings.ark_model_vision,
            )
        else:
            if not settings.zhipu_api_key:
                raise AIServiceUnavailable(
                    "VISION_PROVIDER=zhipu 需要配置 ZHIPU_API_KEY 环境变量。"
                )
            client = ZhipuVisionClient(
                api_key=settings.zhipu_api_key,
                base_url=settings.zhipu_base_url,
                model=settings.zhipu_model_vision,
            )

        mode = settings.image_extract_mode.strip().lower()
        if mode == "vision_text":
            logger.info("image_extract_mode=vision_text (two-step: vision OCR + deepseek structuring)")
            return ZhipuVisionTextClient(client)

        # Default: full vision extraction
        return client

    raise AIServiceUnavailable(
        f"Unknown VISION_PROVIDER {provider!r}. Valid values: 'mock', 'zhipu', 'doubao'."
    )
