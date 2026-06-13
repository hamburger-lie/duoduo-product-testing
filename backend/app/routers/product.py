from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache
from app.core.deps import get_db_session
from app.core.rate_limit import RateLimiter
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.product import (
    ImageExtractRequest,
    ImageExtractResponse,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUploadUrlRequest,
    ProductUploadUrlResponse,
)
from app.services.product_image_extract_service import ProductImageExtractService
from app.services.product_service import ProductService

router = APIRouter(prefix="/api/v1/products", tags=["products"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
product_list_cache = RedisCache(prefix="products")
PRODUCT_LIST_CACHE_TTL_SECONDS = 60

# AI-backed endpoints: 5 req/min per user (vision API calls are expensive)
extract_rate_limit_dependency = Depends(RateLimiter("gen"))


def _product_list_cache_key(*, user_id: int, cursor: str | None, limit: int) -> str:
    return f"user:{user_id}:cursor:{cursor or ''}:limit:{limit}"


@router.post("/upload-url", response_model=ProductUploadUrlResponse)
async def create_product_upload_url(
    payload: ProductUploadUrlRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ProductUploadUrlResponse:
    """Return a mock upload URL for a product image."""

    _ = current_user
    return ProductService(session).create_upload_url(payload)


@router.post("/extract-from-images", response_model=ImageExtractResponse)
async def extract_product_from_images(
    payload: ImageExtractRequest,
    current_user: User = current_user_dependency,
    _rl: None = extract_rate_limit_dependency,
) -> ImageExtractResponse:
    """Extract product fields from image URLs using vision AI.

    Returns candidate field values for user confirmation.
    Does NOT create a Product record.

    Rate-limited to prevent cost-abuse (each call triggers paid AI API requests).
    """

    _ = current_user
    return await ProductImageExtractService().extract(payload)


@router.post("", response_model=ProductResponse)
async def create_product(
    payload: ProductCreateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ProductResponse:
    """Create a product with mock AI understanding."""

    response = await ProductService(session).create_product(user=current_user, payload=payload)
    await product_list_cache.delete_pattern(f"user:{current_user.id}:*")
    return response


@router.get("", response_model=ProductListResponse)
async def list_products(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ProductListResponse:
    """List the current user's products."""

    cache_key = _product_list_cache_key(
        user_id=current_user.id,
        cursor=cursor,
        limit=limit,
    )
    hit, cached = await product_list_cache.get(cache_key)
    if hit:
        return ProductListResponse.model_validate(cached)

    response = await ProductService(session).list_products(
        user=current_user,
        cursor=cursor,
        limit=limit,
    )
    await product_list_cache.set(
        cache_key,
        response.model_dump(mode="json"),
        ttl=PRODUCT_LIST_CACHE_TTL_SECONDS,
    )
    return response


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ProductResponse:
    """Return one product owned by the current user."""

    return await ProductService(session).get_product(user=current_user, product_id=product_id)


@router.post("/{product_id}/reanalyze", response_model=ProductResponse)
async def reanalyze_product(
    product_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ProductResponse:
    """Refresh mock product understanding."""

    response = await ProductService(session).reanalyze_product(
        user=current_user,
        product_id=product_id,
    )
    await product_list_cache.delete_pattern(f"user:{current_user.id}:*")
    return response
