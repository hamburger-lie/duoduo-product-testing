from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
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
) -> ImageExtractResponse:
    """Extract product fields from image URLs using vision AI.

    Returns candidate field values for user confirmation.
    Does NOT create a Product record.
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

    return await ProductService(session).create_product(user=current_user, payload=payload)


@router.get("", response_model=ProductListResponse)
async def list_products(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ProductListResponse:
    """List the current user's products."""

    return await ProductService(session).list_products(
        user=current_user,
        cursor=cursor,
        limit=limit,
    )


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

    return await ProductService(session).reanalyze_product(user=current_user, product_id=product_id)
