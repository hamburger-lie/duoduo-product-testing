"""Internal endpoint for local-dev image storage.

Activated only when STORAGE_ADAPTER=local.  In production (real TOS),
this router is never reached.

PUT  /api/v1/internal/product-images/{key:path}
    Stores raw image bytes sent by the WeChat miniprogram upload flow.

GET  /api/v1/internal/product-images/{key:path}
    Serves stored image bytes back (used by vision extraction chain).

No authentication is required — requests come from the miniprogram (PUT)
or from the backend itself (GET via httpx in vision_client).  Access is
safe in local dev because this endpoint only exists when STORAGE_ADAPTER=local.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse, Response

from app.core.exceptions import AppException

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


def _storage_root() -> Path:
    """Import-time-safe accessor so tests can monkeypatch local_upload.STORAGE_ROOT."""
    from app.storage.local_upload import STORAGE_ROOT

    return STORAGE_ROOT


def _resolve_path(key: str) -> Path:
    from app.storage.local_upload import resolve_local_path

    return resolve_local_path(key)


@router.put(
    "/product-images/{key:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[local-dev] Upload product image bytes",
)
async def upload_local_product_image(key: str, request: Request) -> Response:
    """Receive raw image bytes and persist to local temp directory.

    This endpoint replaces the TOS pre-signed PUT in local development.
    """
    body = await request.body()
    if not body:
        raise AppException(
            code="EMPTY_UPLOAD",
            message="Upload body is empty",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    dest = _resolve_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/product-images/{key:path}",
    summary="[local-dev] Serve stored product image",
)
async def serve_local_product_image(key: str) -> FileResponse:
    """Serve a previously stored product image from local temp directory.

    Called by the backend vision_client when downloading images for base64
    conversion before sending to Zhipu.
    """
    path = _resolve_path(key)
    if not path.exists() or not path.is_file():
        raise AppException(
            code="IMAGE_NOT_FOUND",
            message=f"Local image not found: {key}",
            http_status=status.HTTP_404_NOT_FOUND,
        )
    # Detect MIME from extension; fall back to image/jpeg
    mime, _ = mimetypes.guess_type(str(path))
    media_type = mime if mime and mime.startswith("image/") else "image/jpeg"
    return FileResponse(path, media_type=media_type)
