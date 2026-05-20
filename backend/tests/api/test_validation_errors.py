"""API E2E: input validation and error response format."""
from __future__ import annotations

from httpx import AsyncClient

from tests.api.conftest import login


async def test_product_missing_description(api_client: AsyncClient) -> None:
    headers = await login(api_client, "validation_user")
    resp = await api_client.post(
        "/api/v1/products",
        json={"name": "X", "image_object_keys": ["test.jpg"]},
        headers=headers,
    )
    assert resp.status_code in {400, 422}  # 400 if business validation, 422 if schema


async def test_product_description_too_short(api_client: AsyncClient) -> None:
    headers = await login(api_client, "validation_user_2")
    resp = await api_client.post(
        "/api/v1/products",
        json={"name": "X", "description": "短", "image_object_keys": ["test.jpg"]},
        headers=headers,
    )
    assert resp.status_code in {400, 422}


async def test_product_no_images(api_client: AsyncClient) -> None:
    headers = await login(api_client, "validation_user_3")
    resp = await api_client.post(
        "/api/v1/products",
        json={
            "name": "无图产品",
            "description": "这个产品没有提供任何图片，应该被拒绝创建。",
        },
        headers=headers,
    )
    assert resp.status_code in {400, 422}


async def test_evaluation_nonexistent_product(api_client: AsyncClient) -> None:
    headers = await login(api_client, "validation_user_4")
    resp = await api_client.post(
        "/api/v1/evaluations",
        json={"product_id": 999999},
        headers=headers,
    )
    assert resp.status_code in {400, 404}  # 400 if business error, 404 if not found


async def test_run_evaluation_without_survey(api_client: AsyncClient) -> None:
    """Cannot run evaluation before survey is generated."""
    headers = await login(api_client, "no_survey_user")
    resp = await api_client.post(
        "/api/v1/products",
        json={
            "name": "未生成问卷",
            "description": "用于测试未生成问卷时运行评估是否被正确拦截。",
            "image_object_keys": ["test.jpg"],
        },
        headers=headers,
    )
    product_id = resp.json()["id"]

    resp = await api_client.post(
        "/api/v1/evaluations",
        json={"product_id": product_id},
        headers=headers,
    )
    eval_id = resp.json()["id"]

    resp = await api_client.post(
        f"/api/v1/evaluations/{eval_id}/run", headers=headers,
    )
    assert resp.status_code in {400, 409}  # 400 or 409 for missing prerequisites


async def test_upload_url_invalid_mime(api_client: AsyncClient) -> None:
    headers = await login(api_client, "upload_user")
    resp = await api_client.post(
        "/api/v1/products/upload-url",
        json={"filename": "test.exe", "mime_type": "application/exe", "size_bytes": 100},
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


async def test_upload_url_file_too_large(api_client: AsyncClient) -> None:
    headers = await login(api_client, "upload_user_2")
    resp = await api_client.post(
        "/api/v1/products/upload-url",
        json={
            "filename": "big.jpg",
            "mime_type": "image/jpeg",
            "size_bytes": 10 * 1024 * 1024,  # 10MB > 5MB limit
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "FILE_TOO_LARGE"


async def test_error_response_format(api_client: AsyncClient) -> None:
    """All error responses should have consistent format."""
    headers = await login(api_client, "error_format_user")

    resp = await api_client.get("/api/v1/products/999999", headers=headers)
    assert resp.status_code == 404
    body = resp.json()
    assert "code" in body
    assert "message" in body
