from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProductUploadUrlRequest(BaseModel):
    """Product image upload URL request."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    mime_type: str
    size_bytes: int = Field(ge=0)


class ProductUploadUrlResponse(BaseModel):
    """Product image upload URL response.

    Fields:
    - ``upload_url``: presigned PUT URL the client should use to upload the file.
    - ``image_url``: public or signed GET URL the backend can later download for AI vision.
      Clients MUST use this field; do NOT derive an image URL from upload_url.
    - ``object_key``: storage key to reference this image in subsequent API calls.
    """

    model_config = ConfigDict(extra="forbid")

    upload_url: str
    method: str
    headers: dict[str, str]
    object_key: str
    expires_in: int
    image_url: str


class ProductCreateRequest(BaseModel):
    """Product creation request.

    Images can be supplied in two ways (not mutually exclusive):
    - ``image_object_keys``: object keys from a prior upload-url flow
    - ``image_base64_list``: raw base64 strings or data-URLs sent directly

    At least one of the two must be non-empty.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=128)
    description: str = Field(min_length=10, max_length=500)
    image_object_keys: list[str] = Field(default_factory=list, max_length=5)
    image_base64_list: list[str] | None = Field(
        default=None,
        max_length=5,
        description=(
            "Base64-encoded images (raw base64, data-URL, or HTTPS URL). "
            "Max 5 images. Each string must be under 8 MB."
        ),
    )
    brand: str | None = Field(default=None, max_length=64)
    price: Decimal | None = None
    target_channel: str | None = Field(default=None, max_length=32)


class ProductAiSummary(BaseModel):
    """Structured product understanding from AI or mock."""

    model_config = ConfigDict(extra="ignore")

    main_selling_points: list[str] = Field(default_factory=list)
    key_ingredients: list[str] = Field(default_factory=list)
    suitable_skin_types: list[str] = Field(default_factory=list)
    target_audience: str = ""
    competitive_position: str = ""
    category: str | None = None
    sub_category: str | None = None
    brand: str | None = None
    price: float | None = None
    price_range: str | None = None
    target_channel: str | None = None
    claims_detected: list[str] = Field(default_factory=list)
    risk_or_uncertainty_points: list[str] = Field(default_factory=list)
    usage_scenarios: list[str] = Field(default_factory=list)
    questionnaire_focus: list[str] = Field(default_factory=list)
    confidence: float | None = None


class ProductResponse(BaseModel):
    """Product response aligned to the API contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    image_urls: list[str]
    category: str | None
    sub_category: str | None
    brand: str | None
    price: Decimal | None
    price_range: str | None
    target_channel: str | None
    ai_summary: ProductAiSummary
    status: str
    created_at: str


class ProductListResponse(BaseModel):
    """Cursor-paginated product list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProductResponse]
    next_cursor: str | None
    has_more: bool


class ImageExtractRequest(BaseModel):
    """Request body for extracting product fields from images."""

    model_config = ConfigDict(extra="forbid")

    image_urls: list[str] = Field(min_length=1, max_length=5, description="公开可访问的图片 URL 列表，1–5 张")
    target_fields: list[str] = Field(
        default_factory=list,
        description="希望识别的字段列表；空列表表示识别所有已知字段",
    )
    locale: str = Field(default="zh-CN", max_length=16, description="期望识别语言")


class ExtractedFieldValue(BaseModel):
    """Single extracted field with confidence metadata."""

    model_config = ConfigDict(extra="forbid")

    value: Any = Field(description="识别到的字段值；未识别到时为 null 或空数组")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0–1")
    source: str = Field(description="识别来源，如 image_ocr / llm_inference / vision_llm")


class ImageExtractResponse(BaseModel):
    """Response for POST /products/extract-from-images."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="固定为 ok")
    source_image_count: int = Field(ge=0)
    raw_text: str | None = Field(default=None, description="多模态模型从图片中提取的原始文字；可为空")
    fields: dict[str, ExtractedFieldValue] = Field(description="字段名 → 识别结果；结构稳定，未识别字段值为 null")
    suggested_description: str | None = Field(default=None, description="AI 根据识别内容生成的产品描述建议")
    needs_review: bool = Field(description="是否存在低置信度字段，需前端提示用户确认")


JsonDict = dict[str, Any]
