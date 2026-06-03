from __future__ import annotations

from typing import Protocol

from app.schemas.product import ProductUploadUrlResponse
from app.storage.mock_upload import create_mock_upload_url

__all__ = [
    "ProductStorageAdapter",
    "MockProductStorageAdapter",
    "LocalProductStorageAdapter",
    "TosProductStorageAdapter",
]


class ProductStorageAdapter(Protocol):
    """Storage boundary used by product upload flows.

    ``create_upload_url`` returns a ``ProductUploadUrlResponse`` that includes:
    - ``upload_url``  — presigned PUT URL the client should PUT the file to.
    - ``image_url``   — URL the *backend* can later GET/download the image from.
    - ``object_key``  — storage key to reference this image in API calls.

    Implementations MUST populate ``image_url`` with a URL that is downloadable
    by the backend server (not necessarily by Zhipu directly — vision_client
    will download it first and convert to base64).
    """

    def create_upload_url(
        self,
        *,
        filename: str,
        mime_type: str,
    ) -> ProductUploadUrlResponse:
        """Create an upload URL for a product image."""

    def build_public_url(self, object_key: str) -> str:
        """Build a URL for a stored product image (for display, not for AI)."""


class MockProductStorageAdapter:
    """Fake storage adapter for test / no-cloud development.

    Returns mock-tos.local upload URLs (frontend skips real PUT) and
    mock-cdn.local image URLs (blocked in zhipu mode — expected behaviour).
    """

    def create_upload_url(
        self,
        *,
        filename: str,
        mime_type: str,
    ) -> ProductUploadUrlResponse:
        return create_mock_upload_url(filename=filename, mime_type=mime_type)

    def build_public_url(self, object_key: str) -> str:
        return f"https://mock-cdn.local/{object_key}"


class LocalProductStorageAdapter:
    """Development storage adapter that saves images on the backend host.

    Files are stored in a temp directory and served via the internal
    ``/api/v1/internal/product-images/{key}`` endpoint.  Both upload_url and
    image_url point to that endpoint (PUT to upload, GET to retrieve).

    The backend can therefore download the image from itself, which is
    required for the vision extraction chain.

    NOT suitable for production (single-host, temp dir is wiped on reboot).
    """

    def __init__(self, backend_base_url: str) -> None:
        self._backend_base_url = backend_base_url.rstrip("/")

    def create_upload_url(
        self,
        *,
        filename: str,
        mime_type: str,
    ) -> ProductUploadUrlResponse:
        from app.storage.local_upload import create_local_upload_url

        return create_local_upload_url(
            filename=filename,
            mime_type=mime_type,
            backend_base_url=self._backend_base_url,
        )

    def build_public_url(self, object_key: str) -> str:
        from app.storage.local_upload import _INTERNAL_PATH_PREFIX

        return f"{self._backend_base_url}{_INTERNAL_PATH_PREFIX}/{object_key}"


class TosProductStorageAdapter:
    """Production storage adapter backed by Volcengine TOS.

    Requires TOS_ACCESS_KEY, TOS_SECRET_KEY, TOS_ENDPOINT, TOS_REGION,
    TOS_BUCKET to be configured.  Optionally TOS_CDN_DOMAIN for public-read
    buckets (no presigned GET needed).

    image_url is:
    - public CDN URL when TOS_CDN_DOMAIN is set
    - presigned GET URL when bucket is private
    """

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        endpoint: str,
        region: str,
        bucket: str,
        cdn_domain: str = "",
        presign_expire_seconds: int = 3600,
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._endpoint = endpoint
        self._region = region
        self._bucket = bucket
        self._cdn_domain = cdn_domain
        self._presign_expire_seconds = presign_expire_seconds

    def create_upload_url(
        self,
        *,
        filename: str,
        mime_type: str,
    ) -> ProductUploadUrlResponse:
        from app.storage.tos_upload import create_tos_upload_url

        return create_tos_upload_url(
            filename=filename,
            mime_type=mime_type,
            access_key=self._access_key,
            secret_key=self._secret_key,
            endpoint=self._endpoint,
            region=self._region,
            bucket=self._bucket,
            cdn_domain=self._cdn_domain,
            presign_expire_seconds=self._presign_expire_seconds,
        )

    def build_public_url(self, object_key: str) -> str:
        if self._cdn_domain:
            cdn = self._cdn_domain.rstrip("/")
            if not cdn.startswith("http"):
                cdn = f"https://{cdn}"
            return f"{cdn}/{object_key}"
        # Private bucket: generate a presigned GET URL on demand
        from app.storage.tos_upload import create_tos_upload_url  # reuse client logic

        # For display-only URLs we generate a presigned GET separately
        try:
            import tos  # type: ignore[import-not-found]

            client = tos.TosClientV2(
                ak=self._access_key,
                sk=self._secret_key,
                endpoint=self._endpoint,
                region=self._region,
            )
            result = client.pre_signed_url(
                method=tos.HttpMethodType.Http_Method_Get,
                bucket=self._bucket,
                key=object_key,
                expires=self._presign_expire_seconds,
            )
            return result.signed_url
        except Exception:
            return f"https://{self._endpoint}/{self._bucket}/{object_key}"
