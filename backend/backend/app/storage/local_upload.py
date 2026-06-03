"""Local filesystem storage adapter for development.

Images are saved to a temp directory on the backend host and served by an
internal FastAPI endpoint. This removes the need for real cloud storage when
running locally.

NEVER use this adapter in production — use a real cloud storage adapter.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePath

from app.schemas.product import ProductUploadUrlResponse
from app.utils.ids import generate_snowflake_like_id

# Temporary directory shared between upload and serve endpoints
STORAGE_ROOT: Path = Path(tempfile.gettempdir()) / "duoduo_product_images"

# Internal route prefix (must match internal_images router)
_INTERNAL_PATH_PREFIX = "/api/v1/internal/product-images"


def resolve_local_path(object_key: str) -> Path:
    """Return the absolute filesystem path for a given object_key."""
    # Prevent path-traversal: strip leading slashes and collapse ".."
    safe = PurePath(object_key.lstrip("/")).parts
    # Reject traversal attempts
    sanitized = "/".join(p for p in safe if p not in (".", ".."))
    return STORAGE_ROOT / sanitized


def create_local_upload_url(
    *,
    filename: str,
    mime_type: str,
    backend_base_url: str,
) -> ProductUploadUrlResponse:
    """Generate a local-backend upload URL that stores files in STORAGE_ROOT.

    Both ``upload_url`` and ``image_url`` point to the same backend endpoint;
    PUT writes the file, GET reads it back.
    """
    now = datetime.now(UTC)
    safe_filename = PurePath(filename).name.replace(" ", "_")
    object_key = (
        f"products/{now:%Y/%m}/{generate_snowflake_like_id()}_{safe_filename}"
    )
    base = backend_base_url.rstrip("/")
    endpoint_url = f"{base}{_INTERNAL_PATH_PREFIX}/{object_key}"

    return ProductUploadUrlResponse(
        upload_url=endpoint_url,
        method="PUT",
        headers={"Content-Type": mime_type},
        object_key=object_key,
        expires_in=600,
        image_url=endpoint_url,
    )
