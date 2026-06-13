from __future__ import annotations

from app.storage.adapters import MockProductStorageAdapter


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


def test_mock_storage_adapter_builds_existing_public_url_shape() -> None:
    adapter = MockProductStorageAdapter()

    public_url = adapter.build_public_url("products/2026/05/example_front.jpg")

    assert public_url == "https://mock-cdn.local/products/2026/05/example_front.jpg"
