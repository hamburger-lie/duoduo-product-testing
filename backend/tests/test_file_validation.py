"""Tests for file magic number validation."""
from __future__ import annotations

import base64

from app.storage.file_validation import is_allowed_mime_type, validate_base64_image


def _b64(header_bytes: bytes, pad_to: int = 64) -> str:
    """Create a base64 string with given header bytes, padded."""
    data = header_bytes + b"\x00" * (pad_to - len(header_bytes))
    return base64.b64encode(data).decode()


def test_valid_jpeg() -> None:
    b64 = _b64(b"\xff\xd8\xff\xe0")
    assert validate_base64_image(b64) == "image/jpeg"


def test_valid_png() -> None:
    b64 = _b64(b"\x89PNG\r\n\x1a\n")
    assert validate_base64_image(b64) == "image/png"


def test_valid_gif87a() -> None:
    b64 = _b64(b"GIF87a")
    assert validate_base64_image(b64) == "image/gif"


def test_valid_gif89a() -> None:
    b64 = _b64(b"GIF89a")
    assert validate_base64_image(b64) == "image/gif"


def test_valid_webp() -> None:
    header = b"RIFF\x00\x00\x00\x00WEBP"
    b64 = _b64(header)
    assert validate_base64_image(b64) == "image/webp"


def test_valid_bmp() -> None:
    b64 = _b64(b"BM\x00\x00\x00\x00")
    assert validate_base64_image(b64) == "image/bmp"


def test_invalid_exe_rejected() -> None:
    b64 = _b64(b"MZ\x90\x00")  # PE executable header
    assert validate_base64_image(b64) is None


def test_invalid_random_bytes_rejected() -> None:
    b64 = _b64(b"\x00\x01\x02\x03\x04\x05")
    assert validate_base64_image(b64) is None


def test_data_url_prefix_stripped() -> None:
    raw = _b64(b"\xff\xd8\xff\xe0")
    data_url = f"data:image/jpeg;base64,{raw}"
    assert validate_base64_image(data_url) == "image/jpeg"


def test_claimed_mime_mismatch_rejected() -> None:
    b64 = _b64(b"\xff\xd8\xff\xe0")  # JPEG header
    assert validate_base64_image(b64, claimed_mime="image/png") is None


def test_claimed_mime_match_accepted() -> None:
    b64 = _b64(b"\xff\xd8\xff\xe0")
    assert validate_base64_image(b64, claimed_mime="image/jpeg") == "image/jpeg"


def test_invalid_base64_rejected() -> None:
    assert validate_base64_image("not-valid-base64!!!") is None


def test_is_allowed_mime_type() -> None:
    assert is_allowed_mime_type("image/jpeg") is True
    assert is_allowed_mime_type("image/png") is True
    assert is_allowed_mime_type("application/exe") is False
    assert is_allowed_mime_type("text/html") is False
