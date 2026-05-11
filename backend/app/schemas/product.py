from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProductUploadUrlRequest(BaseModel):
    """Product image upload URL request."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    mime_type: str
    size_bytes: int = Field(gt=0)


class ProductUploadUrlResponse(BaseModel):
    """Mock product image upload URL response."""

    model_config = ConfigDict(extra="forbid")

    upload_url: str
    method: str
    headers: dict[str, str]
    object_key: str
    expires_in: int


class ProductCreateRequest(BaseModel):
    """Product creation request."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=128)
    description: str = Field(min_length=10, max_length=500)
    image_object_keys: list[str] = Field(min_length=1, max_length=5)
    brand: str | None = Field(default=None, max_length=64)
    price: Decimal | None = None
    target_channel: str | None = Field(default=None, max_length=32)


class ProductAiSummary(BaseModel):
    """Mock product understanding summary."""

    model_config = ConfigDict(extra="forbid")

    main_selling_points: list[str]
    key_ingredients: list[str]
    suitable_skin_types: list[str]
    target_audience: str
    competitive_position: str


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


JsonDict = dict[str, Any]
