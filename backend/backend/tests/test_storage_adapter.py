from __future__ import annotations

import pytest
from unittest.mock import patch

from app.storage.adapters import LocalProductStorageAdapter, MockProductStorageAdapter, TosProductStorageAdapter


# ---------------------------------------------------------------------------
# Mock adapter
# ---------------------------------------------------------------------------


def test_mock_storage_adapter_preserves_upload_contract() -> None:
    adapter = MockProductStorageAdapter()

    response = adapter.create_upload_url(
        filename="front image.jpg",
        mime_type="image/jpeg",
    )

    assert response.upload_url.startswith("https://mock-tos.local/products/")
    assert response.method == "PUT"
    assert response.headers == {"Content-Type": "image/jpeg"}
    assert response.object_key.startswith("products/")
    assert response.object_key.endswith("_front_image.jpg")
    assert response.expires_in == 600


def test_mock_storage_adapter_returns_image_url() -> None:
    """image_url must be present and point to mock-cdn.local."""
    adapter = MockProductStorageAdapter()
    response = adapter.create_upload_url(filename="test.jpg", mime_type="image/jpeg")
    assert response.image_url.startswith("https://mock-cdn.local/products/")
    assert response.image_url.endswith(response.object_key.split("/")[-1])


def test_mock_storage_adapter_builds_existing_public_url_shape() -> None:
    adapter = MockProductStorageAdapter()

    public_url = adapter.build_public_url("products/2026/05/example_front.jpg")

    assert public_url == "https://mock-cdn.local/products/2026/05/example_front.jpg"


# ---------------------------------------------------------------------------
# Local adapter
# ---------------------------------------------------------------------------


def test_local_storage_adapter_upload_url_points_to_backend() -> None:
    adapter = LocalProductStorageAdapter("http://127.0.0.1:8000")
    response = adapter.create_upload_url(filename="loreal.jpg", mime_type="image/jpeg")

    assert response.upload_url.startswith(
        "http://127.0.0.1:8000/api/v1/internal/product-images/products/"
    )
    assert response.method == "PUT"
    assert response.object_key.startswith("products/")
    assert response.expires_in == 600


def test_local_storage_adapter_image_url_equals_upload_url() -> None:
    """For local dev, image_url and upload_url point to the same backend endpoint."""
    adapter = LocalProductStorageAdapter("http://127.0.0.1:8000")
    response = adapter.create_upload_url(filename="test.png", mime_type="image/png")

    assert response.image_url == response.upload_url
    assert "mock-cdn.local" not in response.image_url
    assert "mock-tos.local" not in response.upload_url


def test_local_storage_adapter_build_public_url() -> None:
    adapter = LocalProductStorageAdapter("http://127.0.0.1:8000")
    url = adapter.build_public_url("products/2026/06/test.jpg")

    assert url == "http://127.0.0.1:8000/api/v1/internal/product-images/products/2026/06/test.jpg"


def test_local_storage_adapter_strips_trailing_slash() -> None:
    adapter = LocalProductStorageAdapter("http://127.0.0.1:8000/")
    response = adapter.create_upload_url(filename="img.jpg", mime_type="image/jpeg")
    # Should not have double slashes
    assert "//api" not in response.upload_url


# ---------------------------------------------------------------------------
# _make_storage_adapter factory
# ---------------------------------------------------------------------------


def test_make_storage_adapter_returns_mock_by_default() -> None:
    from app.services.product_service import _make_storage_adapter

    class FakeSettings:
        storage_adapter = "mock"
        backend_base_url = "http://127.0.0.1:8000"
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeSettings()):
        adapter = _make_storage_adapter()
    assert isinstance(adapter, MockProductStorageAdapter)


def test_make_storage_adapter_returns_local_when_configured() -> None:
    from app.services.product_service import _make_storage_adapter

    class FakeSettings:
        storage_adapter = "local"
        backend_base_url = "http://127.0.0.1:9999"
        app_env = "development"

    with patch("app.core.config.get_settings", return_value=FakeSettings()):
        adapter = _make_storage_adapter()
    assert isinstance(adapter, LocalProductStorageAdapter)


def test_make_storage_adapter_local_raises_in_production() -> None:
    """STORAGE_ADAPTER=local must not be used in production."""
    from app.services.product_service import _make_storage_adapter

    class FakeProdSettings:
        storage_adapter = "local"
        backend_base_url = "http://127.0.0.1:8000"
        app_env = "production"

    with patch("app.core.config.get_settings", return_value=FakeProdSettings()):
        with pytest.raises(RuntimeError, match="STORAGE_ADAPTER=local"):
            _make_storage_adapter()


def test_make_storage_adapter_tos_missing_credentials_raises() -> None:
    """STORAGE_ADAPTER=tos without credentials → RuntimeError."""
    from app.services.product_service import _make_storage_adapter

    class FakeTosSettings:
        storage_adapter = "tos"
        app_env = "production"
        tos_access_key = ""
        tos_secret_key = ""
        tos_endpoint = ""
        tos_region = ""
        tos_bucket = ""
        tos_cdn_domain = ""
        tos_presign_expire_seconds = 3600

    with patch("app.core.config.get_settings", return_value=FakeTosSettings()):
        with pytest.raises(RuntimeError, match="TOS_ACCESS_KEY"):
            _make_storage_adapter()


def test_make_storage_adapter_tos_with_credentials_returns_tos_adapter() -> None:
    """STORAGE_ADAPTER=tos with full credentials → TosProductStorageAdapter."""
    from app.services.product_service import _make_storage_adapter

    class FakeTosSettings:
        storage_adapter = "tos"
        app_env = "production"
        tos_access_key = "AK_TEST"
        tos_secret_key = "SK_TEST"
        tos_endpoint = "tos-cn-beijing.volces.com"
        tos_region = "cn-beijing"
        tos_bucket = "test-bucket"
        tos_cdn_domain = "cdn.example.com"
        tos_presign_expire_seconds = 3600

    with patch("app.core.config.get_settings", return_value=FakeTosSettings()):
        adapter = _make_storage_adapter()
    assert isinstance(adapter, TosProductStorageAdapter)
