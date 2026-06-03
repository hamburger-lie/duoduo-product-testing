from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePath

from app.schemas.product import ProductUploadUrlResponse
from app.utils.ids import generate_snowflake_like_id


def create_mock_upload_url(*, filename: str, mime_type: str) -> ProductUploadUrlResponse:
    """Create a mock TOS-style upload URL without calling external services."""

    now = datetime.now(UTC)
    safe_filename = PurePath(filename).name.replace(" ", "_")
    object_key = (
        f"products/{now:%Y/%m}/{generate_snowflake_like_id()}_{safe_filename}"
    )
    return ProductUploadUrlResponse(
        upload_url=f"https://mock-tos.local/{object_key}",
        method="PUT",
        headers={"Content-Type": mime_type},
        object_key=object_key,
        expires_in=600,
        # Mock CDN URL — blocked by vision_client in zhipu mode (expected).
        image_url=f"https://mock-cdn.local/{object_key}",
    )
