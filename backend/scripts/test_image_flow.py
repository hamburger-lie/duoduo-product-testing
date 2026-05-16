"""测试两种产品创建方式：
  方式 1 — image_object_keys（mock 上传流）
  方式 2 — image_base64_list（直接传 base64，走 GLM-4.6V 视觉）

用法：
    uv run pytest scripts/test_image_flow.py -s        # 跑全部
    uv run pytest scripts/test_image_flow.py -s -k vision  # 只跑视觉
"""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def _fix_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _encode_image(path: str | Path) -> str:
    """读取本地图片，返回 base64 字符串。"""
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode()


def _encode_url_image(url: str) -> str:
    """直接返回 URL（支持 HTTPS URL 传给 GLM-4.6V）。"""
    return url


# --------------------------------------------------------------------------- #
# 测试：方式 1 — image_object_keys（mock flow）
# --------------------------------------------------------------------------- #

async def test_method1_object_keys() -> None:
    """方式 1：先拿 upload-url，再用 object_key 创建产品（mock CDN）。"""
    from httpx import AsyncClient

    from app.main import app

    print("\n" + "=" * 60)
    print("方式 1：image_object_keys (mock CDN 上传流)")
    print("=" * 60)

    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1) 登录
        r = await client.post(
            "/api/v1/auth/wechat/login", json={"code": "test_flow_m1"}
        )
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2) 申请上传 URL
        r = await client.post(
            "/api/v1/products/upload-url",
            headers=headers,
            json={
                "filename": "product.jpg",
                "mime_type": "image/jpeg",
                "size_bytes": 1024,
            },
        )
        assert r.status_code == 200, r.text
        upload_data = r.json()
        object_key = upload_data["object_key"]
        print(f"  → upload-url 返回 object_key: {object_key}")

        # 3) 用 object_key 创建产品
        r = await client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "name": "珀莱雅红宝石面霜",
                "description": "六胜肽+A醇双抗老面霜，价格239元，适合熟龄肌。",
                "image_object_keys": [object_key],
                "brand": "珀莱雅",
                "price": 239,
            },
        )
        assert r.status_code == 200, r.text
        product = r.json()
        print(f"  → 产品 ID: {product['id']}")
        print(f"  → 分类: {product['category']}")
        print(f"  → ai_summary.main_selling_points: {product['ai_summary']['main_selling_points']}")
        print("  → [方式 1] OK ✓")


# --------------------------------------------------------------------------- #
# 测试：方式 2 — image_base64_list（视觉识别）
# --------------------------------------------------------------------------- #

async def test_method2_base64_image(image_source: str) -> None:
    """方式 2：直接传 base64（或 HTTPS URL），走 GLM-4.6V 视觉识别。

    image_source 可以是：
    - 本地文件路径（如 /tmp/product.jpg）
    - HTTPS URL（如 https://...）
    - base64 字符串
    """
    from httpx import AsyncClient

    from app.core.config import get_settings
    from app.main import app

    s = get_settings()
    provider = s.ai_provider.strip().lower()
    if provider == "mock":
        print("\n[方式 2] AI_PROVIDER=mock，跳过视觉识别（设置 AI_PROVIDER=deepseek 启用）")
        return

    print("\n" + "=" * 60)
    print("方式 2：image_base64_list (GLM-4.6V 视觉识别)")
    print("=" * 60)

    # 处理图片源
    if image_source.startswith("http"):
        img = image_source  # HTTPS URL 直接传
        print(f"  → 图片来源: URL ({image_source[:60]}...)")
    elif Path(image_source).exists():
        img = _encode_image(image_source)
        print(f"  → 图片来源: 本地文件 {image_source} ({len(img)//1024} KB base64)")
    else:
        img = image_source  # 当作 base64 字符串
        print(f"  → 图片来源: base64 字符串 ({len(img)//1024} KB)")

    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1) 登录
        r = await client.post(
            "/api/v1/auth/wechat/login", json={"code": "test_flow_m2"}
        )
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2) 直接用 base64 创建产品（AI 从图里读信息）
        r = await client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "description": "请根据图片识别产品信息，分析其成分、价格、适用人群和主要卖点。",
                "image_object_keys": [],
                "image_base64_list": [img],
            },
        )
        assert r.status_code == 200, r.text
        product = r.json()
        print(f"  → 产品 ID: {product['id']}")
        print(f"  → 识别名称: {product['name']}")
        print(f"  → 识别品牌: {product.get('brand')}")
        print(f"  → 识别分类: {product['category']}")
        print(f"  → 识别价格: {product.get('price')}")
        ai = product["ai_summary"]
        print(f"  → 关键成分: {ai.get('key_ingredients')}")
        print(f"  → 主要卖点: {ai.get('main_selling_points')}")
        print(f"  → 目标人群: {ai.get('target_audience')}")
        print("  → [方式 2] OK ✓")


# --------------------------------------------------------------------------- #
# 直接运行入口（python scripts/test_image_flow.py [图片路径或URL]）
# --------------------------------------------------------------------------- #

async def _main() -> None:
    _fix_stdout()

    image_source = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "https://img.alicdn.com/imgextra/i4/O1CN01mock-product-image.jpg"
    )

    print("\n[测试开始]")
    await test_method1_object_keys()
    await test_method2_base64_image(image_source)
    print("\n[全部测试通过] ✓")


if __name__ == "__main__":
    asyncio.run(_main())
