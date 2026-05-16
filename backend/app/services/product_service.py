from __future__ import annotations

import logging
from datetime import UTC
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models.product import Product
from app.db.models.user import User
from app.db.repositories.product import ProductRepository
from app.schemas.product import (
    ProductAiSummary,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUploadUrlRequest,
    ProductUploadUrlResponse,
)
from app.storage.adapters import MockProductStorageAdapter, ProductStorageAdapter

if TYPE_CHECKING:
    from app.ai.client import AIClient

ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024

logger = logging.getLogger(__name__)


class ProductService:
    """Product use cases with mock or AI understanding."""

    def __init__(
        self,
        session: AsyncSession,
        ai_client: AIClient | None = None,
        storage_adapter: ProductStorageAdapter | None = None,
    ) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self._ai_client = ai_client
        self._storage_adapter = storage_adapter or MockProductStorageAdapter()

    def create_upload_url(self, payload: ProductUploadUrlRequest) -> ProductUploadUrlResponse:
        """Create a mock upload URL after validating image constraints."""

        if payload.mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise AppException(
                code="INVALID_FILE_TYPE",
                message="Only jpg/png images are allowed",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        if payload.size_bytes > MAX_UPLOAD_SIZE_BYTES:
            raise AppException(
                code="FILE_TOO_LARGE",
                message="File is larger than 5MB",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        return self._storage_adapter.create_upload_url(
            filename=payload.filename,
            mime_type=payload.mime_type,
        )

    async def create_product(self, *, user: User, payload: ProductCreateRequest) -> ProductResponse:
        """Create a product with AI or mock understanding.

        At least one of ``image_object_keys`` or ``image_base64_list`` must
        be provided so there is something meaningful for the AI to work with.
        """

        from app.ai.moderation import get_moderation_adapter

        has_object_keys = bool(payload.image_object_keys)
        has_base64 = bool(payload.image_base64_list)
        if not has_object_keys and not has_base64:
            raise AppException(
                code="IMAGE_REQUIRED",
                message="Provide at least one image via image_object_keys or image_base64_list",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        moderator = get_moderation_adapter()
        await moderator.check_input(
            f"{payload.name or ''} {payload.description or ''}"
        )

        ai_summary = await self._build_ai_summary(user=user, payload=payload)

        category = ai_summary.category or "美妆"
        sub_category = ai_summary.sub_category or "其他"
        price = payload.price
        if price is None and ai_summary.price is not None:
            price = Decimal(str(ai_summary.price))

        product = await self.products.create(
            {
                "user_id": user.id,
                "name": payload.name or self._infer_name(payload.description),
                "description": payload.description,
                "category": category,
                "sub_category": sub_category,
                "brand": payload.brand or ai_summary.brand,
                "price": price,
                "price_range": self._price_range(price) or ai_summary.price_range,
                "target_channel": payload.target_channel or ai_summary.target_channel,
                "image_urls": [
                    self._storage_adapter.build_public_url(key)
                    for key in payload.image_object_keys
                ],
                "ai_summary": ai_summary.model_dump(),
                "status": "ready",
            }
        )
        await self.session.commit()
        return self._to_response(product)

    async def get_product(self, *, user: User, product_id: int) -> ProductResponse:
        """Return one product owned by the current user."""

        product = await self.products.get_by_id_and_user_id(product_id=product_id, user_id=user.id)
        if product is None:
            raise self._not_found(product_id)
        return self._to_response(product)

    async def reanalyze_product(self, *, user: User, product_id: int) -> ProductResponse:
        """Re-run AI product understanding."""

        product = await self.products.get_by_id_and_user_id(product_id=product_id, user_id=user.id)
        if product is None:
            raise self._not_found(product_id)

        payload = ProductCreateRequest(
            name=product.name,
            description=product.description or "",
            image_object_keys=(
                list(product.image_urls) if product.image_urls else ["placeholder.jpg"]
            ),
            brand=product.brand,
            price=product.price,
            target_channel=product.target_channel,
        )
        summary = await self._build_ai_summary(user=user, payload=payload)

        update_fields: dict[str, object] = {
            "ai_summary": summary.model_dump(),
            "status": "ready",
        }
        if summary.category:
            update_fields["category"] = summary.category
        if summary.sub_category:
            update_fields["sub_category"] = summary.sub_category

        await self.products.update(product, update_fields)
        await self.session.commit()
        return self._to_response(product)

    async def list_products(
        self,
        *,
        user: User,
        cursor: str | None,
        limit: int,
    ) -> ProductListResponse:
        """Return a cursor-paginated list of the current user's products."""

        offset = self._decode_cursor(cursor)
        bounded_limit = max(1, min(limit, 100))
        products = await self.products.list_by_user_id(
            user_id=user.id,
            offset=offset,
            limit=bounded_limit + 1,
        )
        has_more = len(products) > bounded_limit
        visible_products = products[:bounded_limit]
        next_cursor = str(offset + bounded_limit) if has_more else None
        return ProductListResponse(
            items=[self._to_response(product) for product in visible_products],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def _to_response(self, product: Product) -> ProductResponse:
        summary = product.ai_summary or self._build_mock_ai_summary_from_product(
            product
        ).model_dump()
        return ProductResponse(
            id=str(product.id),
            name=product.name or "未命名产品",
            description=product.description,
            image_urls=list(product.image_urls),
            category=product.category,
            sub_category=product.sub_category,
            brand=product.brand,
            price=product.price,
            price_range=product.price_range,
            target_channel=product.target_channel,
            ai_summary=ProductAiSummary(**summary),
            status=product.status,
            created_at=product.created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )

    async def _build_ai_summary(
        self,
        *,
        user: User,
        payload: ProductCreateRequest,
    ) -> ProductAiSummary:
        """Route to mock or AI product understanding based on AI_PROVIDER."""

        from app.core.config import get_settings

        if get_settings().ai_provider in {"ark", "deepseek"}:
            return await self._understand_product_with_ai(user=user, payload=payload)
        return self._build_mock_ai_summary(payload)

    async def _understand_product_with_ai(
        self,
        *,
        user: User,
        payload: ProductCreateRequest,
    ) -> ProductAiSummary:
        """Call AI to extract structured product info.

        Two-step when images are present:
          1. GLM-4.6V  → describe visible image content as plain text
          2. DeepSeek  → parse product context + image description into JSON

        Text-only (no images): skip step 1, DeepSeek handles everything.
        This keeps GLM usage minimal (only what it's actually good at) and
        lets the faster/cheaper DeepSeek model do all the reasoning.
        """

        from app.ai.adapters.structured_generation import ProductUnderstandingAdapter

        try:
            adapter = ProductUnderstandingAdapter(ai_client=self._ai_client)
            return await adapter.generate_summary(payload=payload)
        except Exception:
            logger.exception("product_ai_understand_failed")
            raise

    def _build_mock_ai_summary(self, payload: ProductCreateRequest) -> ProductAiSummary:
        """Fallback mock product understanding."""

        ingredients = (
            ["烟酰胺", "神经酰胺"]
            if "烟酰胺" in payload.description
            else ["核心成分待确认"]
        )
        return ProductAiSummary(
            main_selling_points=["温和修护", "日常提亮", "适合快速测品验证"],
            key_ingredients=ingredients,
            suitable_skin_types=["敏感肌", "干性肌", "混合肌"],
            target_audience="关注成分与温和修护的都市护肤用户",
            competitive_position="中端功效护肤测试样品",
        )

    def _build_mock_ai_summary_from_product(self, product: Product) -> ProductAiSummary:
        """Fallback mock for reanalyze."""

        return ProductAiSummary(
            main_selling_points=["重新识别后的温和修护卖点", "保湿与提亮组合"],
            key_ingredients=["烟酰胺", "神经酰胺"],
            suitable_skin_types=["敏感肌", "干性肌", "混合肌"],
            target_audience="关注成分功效和性价比的护肤用户",
            competitive_position=f"{product.category or '美妆'}品类中端测试产品",
        )

    def _infer_name(self, description: str) -> str:
        return description[:20]

    def _price_range(self, price: Decimal | None) -> str | None:
        if price is None:
            return None
        if price < 50:
            return "0-50"
        if price < 100:
            return "50-100"
        if price < 200:
            return "100-200"
        if price < 400:
            return "200-400"
        if price < 800:
            return "400-800"
        return "800+"

    def _decode_cursor(self, cursor: str | None) -> int:
        if cursor is None or cursor == "":
            return 0
        if not cursor.isdigit():
            return 0
        return int(cursor)

    def _not_found(self, product_id: int) -> AppException:
        return AppException(
            code="PRODUCT_NOT_FOUND",
            message="Product not found",
            http_status=status.HTTP_404_NOT_FOUND,
            details={"product_id": str(product_id)},
        )
