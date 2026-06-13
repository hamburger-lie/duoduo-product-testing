"""E2E: product understanding now carries appearance into ProductAiSummary."""
from __future__ import annotations

import asyncio
import base64

import httpx

from app.ai.adapters.structured_generation import ProductUnderstandingAdapter
from app.schemas.product import ProductCreateRequest

IMG = "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551395237897_product_1781140476353.jpg"


async def main() -> None:
    async with httpx.AsyncClient() as c:
        r = await c.get(IMG, timeout=30)
        b64 = base64.b64encode(r.content).decode()

    payload = ProductCreateRequest(
        name="兰蔻持妆粉底液",
        description="天猫618 持妆粉底液",
        image_base64_list=[f"data:image/jpeg;base64,{b64}"],
    )
    adapter = ProductUnderstandingAdapter()
    summary = await adapter.generate_summary(payload=payload)
    print("=== appearance ===")
    print(repr(summary.appearance))
    print("=== 其它关键字段 ===")
    print("name:", summary.category, "| selling_points:", summary.main_selling_points[:2])


if __name__ == "__main__":
    asyncio.run(main())
