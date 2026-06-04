"""Tests for avatar upload security — magic-bytes validation, size limits."""
from __future__ import annotations

import io
import struct

import pytest
from httpx import AsyncClient

from tests.api.conftest import login

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Helpers — minimal valid image payloads
# ---------------------------------------------------------------------------


def _minimal_jpeg() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _minimal_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _minimal_webp() -> bytes:
    payload = b"\x00" * 20
    size = len(payload) + 4  # RIFF chunk size
    return b"RIFF" + struct.pack("<I", size) + b"WEBP" + payload


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


async def test_upload_jpeg_succeeds(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_jpeg")
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("photo.jpg", io.BytesIO(_minimal_jpeg()), "image/jpeg")},
    )
    assert resp.status_code == 200
    url = resp.json()["avatar_url"]
    assert url.endswith(".jpg")


async def test_upload_png_succeeds(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_png")
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("photo.png", io.BytesIO(_minimal_png()), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"].endswith(".png")


async def test_upload_webp_succeeds(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_webp")
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("photo.webp", io.BytesIO(_minimal_webp()), "image/webp")},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"].endswith(".webp")


# ---------------------------------------------------------------------------
# Extension determined by magic bytes, NOT filename
# ---------------------------------------------------------------------------


async def test_extension_from_magic_not_filename(api_client: AsyncClient) -> None:
    """filename says .png but payload is JPEG — saved as .jpg."""
    headers = await login(api_client, "avatar_ext_mismatch")
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("photo.png", io.BytesIO(_minimal_jpeg()), "image/png")},
    )
    assert resp.status_code == 200
    assert resp.json()["avatar_url"].endswith(".jpg")


# ---------------------------------------------------------------------------
# Rejection cases
# ---------------------------------------------------------------------------


async def test_html_file_rejected(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_html")
    html = b"<html><body>XSS</body></html>"
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("avatar.html", io.BytesIO(html), "text/html")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


async def test_html_disguised_as_jpg_rejected(api_client: AsyncClient) -> None:
    """filename=avatar.jpg, Content-Type=image/jpeg, but content is HTML."""
    headers = await login(api_client, "avatar_html_jpg")
    html = b"<html><body>XSS</body></html>"
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("avatar.jpg", io.BytesIO(html), "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


async def test_svg_rejected(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_svg")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("avatar.svg", io.BytesIO(svg), "image/svg+xml")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


async def test_php_rejected(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_php")
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("shell.php", io.BytesIO(b"<?php system($_GET['c']); ?>"), "application/x-php")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


async def test_empty_file_rejected(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_empty")
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
    )
    assert resp.status_code == 400


async def test_oversized_file_rejected(api_client: AsyncClient) -> None:
    headers = await login(api_client, "avatar_big")
    big = _minimal_jpeg() + b"\x00" * (2 * 1024 * 1024 + 1)
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("big.jpg", io.BytesIO(big), "image/jpeg")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "FILE_TOO_LARGE"


async def test_gif_rejected(api_client: AsyncClient) -> None:
    """GIF is a valid image but not allowed for avatars."""
    headers = await login(api_client, "avatar_gif")
    gif = b"GIF89a" + b"\x00" * 64
    resp = await api_client.post(
        "/api/v1/auth/avatar",
        headers=headers,
        files={"file": ("avatar.gif", io.BytesIO(gif), "image/gif")},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"
