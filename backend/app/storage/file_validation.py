"""Validate uploaded files by checking magic number (file header).

Only checks the first 16 bytes — no external C dependencies required.
Supported types: JPEG, PNG, GIF, WebP, BMP.
"""
from __future__ import annotations

import base64
import re

MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024
MAX_BASE64_IMAGE_CHARS = 11 * 1024 * 1024
MAX_PDF_BASE64_CHARS = 14 * 1024 * 1024

# Magic number signatures for allowed image types
_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/webp": [b"RIFF"],  # RIFF header; "WEBP" appears at offset 8
    "image/bmp": [b"BM"],
}

# Allowed MIME types for upload-url flow
ALLOWED_MIME_TYPES = frozenset(_MAGIC_SIGNATURES.keys())

# data-URL prefix regex: data:image/jpeg;base64,
_DATA_URL_RE = re.compile(r"^data:[^;]+;base64,", re.IGNORECASE)


def _strip_data_url_prefix(b64_str: str) -> str:
    """Remove optional ``data:...;base64,`` prefix from a base64 string."""
    return _DATA_URL_RE.sub("", b64_str)


def validate_base64_image(b64_str: str, claimed_mime: str | None = None) -> str | None:
    """Validate a base64-encoded image by checking its magic number.

    Returns the detected MIME type on success, or ``None`` if the content
    does not match any allowed image type.

    If *claimed_mime* is given the detected type must match it; otherwise
    ``None`` is returned (mismatch).
    """
    raw_b64 = _strip_data_url_prefix(b64_str)

    try:
        header = base64.b64decode(raw_b64[:64], validate=True)[:16]
    except Exception:
        return None

    detected = validate_image_bytes(header)

    if detected is None:
        return None

    if claimed_mime and detected != claimed_mime:
        return None

    return detected


def validate_image_bytes(file_bytes: bytes, claimed_mime: str | None = None) -> str | None:
    """Validate image bytes by checking their magic number."""

    header = file_bytes[:16]
    detected: str | None = None
    for mime, signatures in _MAGIC_SIGNATURES.items():
        for sig in signatures:
            if header[: len(sig)] == sig:
                if mime == "image/webp" and header[8:12] != b"WEBP":
                    continue
                detected = mime
                break
        if detected:
            break

    if detected is None:
        return None

    if claimed_mime and detected != claimed_mime:
        return None

    return detected


def validate_pdf_bytes(file_bytes: bytes) -> bool:
    """Return True only when bytes look like a PDF document."""

    return file_bytes.startswith(b"%PDF-")


def is_allowed_mime_type(mime_type: str) -> bool:
    """Check whether a MIME type is in the allow-list."""
    return mime_type in ALLOWED_MIME_TYPES
