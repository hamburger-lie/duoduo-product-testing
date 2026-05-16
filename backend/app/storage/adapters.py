from __future__ import annotations

from typing import Protocol

from app.schemas.product import ProductUploadUrlResponse
from app.storage.mock_upload import create_mock_upload_url


class ProductStorageAdapter(Protocol):
    """Storage boundary used by product upload flows."""

    def create_upload_url(
        self,
        *,
        filename: str,
        mime_type: str,
    ) -> ProductUploadUrlResponse:
        """Create an upload URL for a product image."""

    def build_public_url(self, object_key: str) -> str:
        """Build a public URL for a stored product image."""


class MockProductStorageAdapter:
    """Mock storage adapter preserving the current product upload behavior."""

    def create_upload_url(
        self,
        *,
        filename: str,
        mime_type: str,
    ) -> ProductUploadUrlResponse:
        """Create the existing mock upload URL response."""

        return create_mock_upload_url(filename=filename, mime_type=mime_type)

    def build_public_url(self, object_key: str) -> str:
        """Build the existing mock CDN URL shape."""

        return f"https://mock-cdn.local/{object_key}"
