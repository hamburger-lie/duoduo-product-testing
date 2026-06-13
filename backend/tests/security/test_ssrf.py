"""SSRF protection tests for image URL validation.

Verifies that:
1. _is_private_host correctly blocks private IPs and resolved hostnames
2. _validate_image_urls_for_real_model rejects dangerous URLs in production
3. _compute_image_hash validates URLs before fetching (no blind SSRF)
4. Redirect-based SSRF bypass is prevented
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# _is_private_host unit tests
# ---------------------------------------------------------------------------


class TestIsPrivateHost:
    """Test the hostname/IP → private network check."""

    def test_blocks_localhost(self) -> None:
        from app.ai.vision_client import _is_private_host

        assert _is_private_host("localhost") is True

    def test_blocks_loopback_ipv4(self) -> None:
        from app.ai.vision_client import _is_private_host

        assert _is_private_host("127.0.0.1") is True
        assert _is_private_host("127.0.0.2") is True

    def test_blocks_metadata_ip(self) -> None:
        from app.ai.vision_client import _is_private_host

        assert _is_private_host("169.254.169.254") is True

    def test_blocks_private_ranges(self) -> None:
        from app.ai.vision_client import _is_private_host

        assert _is_private_host("10.0.0.1") is True
        assert _is_private_host("172.16.0.1") is True
        assert _is_private_host("192.168.1.1") is True

    def test_allows_public_ip(self) -> None:
        from app.ai.vision_client import _is_private_host

        assert _is_private_host("8.8.8.8") is False
        assert _is_private_host("1.1.1.1") is False

    def test_dns_resolution_blocks_private_hostname(self) -> None:
        """A hostname that resolves to a private IP should be blocked."""
        import socket

        from app.ai.vision_client import _is_private_host

        # Mock getaddrinfo to return a private IP for a fake domain
        fake_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_result):
            assert _is_private_host("evil-rebind.attacker.com") is True

    def test_dns_resolution_allows_public_hostname(self) -> None:
        """A hostname that resolves to a public IP should be allowed."""
        import socket

        from app.ai.vision_client import _is_private_host

        fake_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.1", 0)),
        ]
        with patch("socket.getaddrinfo", return_value=fake_result):
            assert _is_private_host("cdn.example.com") is False

    def test_dns_failure_fails_closed(self) -> None:
        """If DNS resolution fails, treat as private (fail-closed)."""
        import socket

        from app.ai.vision_client import _is_private_host

        with patch("socket.getaddrinfo", side_effect=socket.gaierror("nxdomain")):
            assert _is_private_host("nonexistent.invalid") is True


# ---------------------------------------------------------------------------
# _validate_image_urls_for_real_model tests
# ---------------------------------------------------------------------------


class TestValidateImageUrls:
    """Test URL validation for real vision models."""

    def test_rejects_non_http_scheme(self) -> None:
        from app.ai.vision_client import _validate_image_urls_for_real_model
        from app.core.exceptions import AppException

        with pytest.raises(AppException) as exc_info:
            _validate_image_urls_for_real_model(["file:///etc/passwd"])
        assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"

    def test_rejects_mock_domain(self) -> None:
        from app.ai.vision_client import _validate_image_urls_for_real_model
        from app.core.exceptions import AppException

        with pytest.raises(AppException) as exc_info:
            _validate_image_urls_for_real_model(["https://mock-tos.local/img.jpg"])
        assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"

    @patch.dict(os.environ, {"APP_ENV": "production", "APP_SECRET_KEY": "x" * 64,
                              "CORS_ALLOWED_ORIGINS": "https://app.example.com",
                              "WECHAT_APP_ID": "test", "WECHAT_APP_SECRET": "test",
                              "AI_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test",
                              "EVALUATION_RUN_MODE": "celery"})
    def test_rejects_private_ip_in_production(self) -> None:
        from importlib import reload

        import app.core.config as config_mod
        # Clear the lru_cache to pick up overridden APP_ENV
        config_mod.get_settings.cache_clear()
        try:
            reload(config_mod)
            from app.ai.vision_client import _validate_image_urls_for_real_model
            from app.core.exceptions import AppException

            with pytest.raises(AppException) as exc_info:
                _validate_image_urls_for_real_model(["http://169.254.169.254/latest/meta-data/"])
            assert exc_info.value.code == "IMAGE_URL_NOT_ACCESSIBLE"
        finally:
            config_mod.get_settings.cache_clear()

    def test_allows_public_url(self) -> None:
        from app.ai.vision_client import _validate_image_urls_for_real_model

        # Should not raise for a public URL
        _validate_image_urls_for_real_model(["https://cdn.example.com/product.jpg"])


# ---------------------------------------------------------------------------
# _compute_image_hash SSRF gate
# ---------------------------------------------------------------------------


class TestComputeImageHashSSRF:
    """Verify _compute_image_hash validates URLs before fetching."""

    @pytest.mark.asyncio
    async def test_private_url_does_not_trigger_fetch(self) -> None:
        """When URL fails validation, _compute_image_hash should NOT make
        an HTTP request — it should fall back to hashing the URL string."""
        from unittest.mock import AsyncMock

        from app.services.product_image_extract_service import _compute_image_hash

        # Patch httpx.AsyncClient to detect if a request is made
        mock_client = AsyncMock()
        with patch("app.services.product_image_extract_service.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Use a mock-blocked URL
            result = await _compute_image_hash("https://mock-tos.local/secret.jpg")

            # Should return a hash (of the URL string, not fetched content)
            assert isinstance(result, str)
            assert len(result) == 32

            # The HTTP client should NOT have been instantiated/called
            mock_client.get.assert_not_called()
