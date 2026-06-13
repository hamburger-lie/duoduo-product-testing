"""Volcengine TOS (Tencent Object Storage-compatible) storage adapter.

Provides presigned PUT upload URLs and either presigned GET URLs (private
bucket) or CDN public URLs (public-read bucket) as ``image_url``.

NOT suitable for local development — use LocalProductStorageAdapter instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.product import ProductUploadUrlResponse
from app.utils.ids import generate_snowflake_like_id


def create_tos_upload_url(
    *,
    filename: str,
    mime_type: str,
    access_key: str,
    secret_key: str,
    endpoint: str,
    region: str,
    bucket: str,
    cdn_domain: str,
    presign_expire_seconds: int,
) -> ProductUploadUrlResponse:
    """Generate a presigned TOS PUT URL and the corresponding image_url.

    ``image_url`` is:
    - ``https://{cdn_domain}/{object_key}`` when cdn_domain is set (public-read)
    - A presigned GET URL when cdn_domain is empty (private bucket)

    The SDK call is done lazily so that the import does not fail when the
    volcengine-python-sdk is not installed (local dev with STORAGE_ADAPTER=local).
    """
    try:
        import tos  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "STORAGE_ADAPTER=tos requires the volcengine-python-sdk package. "
            "Install it with: pip install volcengine-python-sdk"
        ) from exc

    from pathlib import PurePath

    now = datetime.now(UTC)
    safe_filename = PurePath(filename).name.replace(" ", "_")
    object_key = f"products/{now:%Y/%m}/{generate_snowflake_like_id()}_{safe_filename}"

    client = tos.TosClientV2(
        ak=access_key,
        sk=secret_key,
        endpoint=endpoint,
        region=region,
    )

    # Presigned PUT URL for upload
    put_result = client.pre_signed_url(
        method=tos.HttpMethodType.Http_Method_Put,
        bucket=bucket,
        key=object_key,
        expires=presign_expire_seconds,
        header={"Content-Type": mime_type},
    )

    # image_url: CDN (public) or presigned GET (private)
    if cdn_domain:
        cdn = cdn_domain.rstrip("/")
        if not cdn.startswith("http"):
            cdn = f"https://{cdn}"
        image_url = f"{cdn}/{object_key}"
    else:
        get_result = client.pre_signed_url(
            method=tos.HttpMethodType.Http_Method_Get,
            bucket=bucket,
            key=object_key,
            expires=presign_expire_seconds,
        )
        image_url = get_result.signed_url

    return ProductUploadUrlResponse(
        upload_url=put_result.signed_url,
        method="PUT",
        headers={"Content-Type": mime_type},
        object_key=object_key,
        expires_in=presign_expire_seconds,
        image_url=image_url,
    )
