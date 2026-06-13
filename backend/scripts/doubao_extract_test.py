"""Test the FULL extract path via factory with VISION_PROVIDER=doubao + thinking off."""
from __future__ import annotations

import asyncio
import os
import time

os.environ["VISION_PROVIDER"] = "doubao"
os.environ["VISION_DISABLE_THINKING"] = "true"

from app.ai.vision_client import ALL_KNOWN_FIELDS, get_vision_extract_client
from app.core import config

IMAGES = [
    "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551395237897_product_1781140476353.jpg",
    "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551711604748_product_1781140553313.jpg",
]


async def main() -> None:
    config.get_settings.cache_clear()
    client = get_vision_extract_client()
    print("client:", type(client).__name__, "| model:", getattr(client, "_model", "?"))
    out = []
    for img in IMAGES:
        for r in range(2):
            t = time.perf_counter()
            try:
                res = await client.extract_fields(
                    image_urls=[img], target_fields=ALL_KNOWN_FIELDS, locale="zh"
                )
                dt = time.perf_counter() - t
                f = res.fields

                def v(k):
                    x = f.get(k)
                    return x.value if x else None
                filled = sum(1 for k in ALL_KNOWN_FIELDS if v(k) not in (None, "", []))
                out.append(
                    f"{img.rsplit('/',1)[-1][:20]} run{r+1} {dt:5.1f}s filled={filled}/9 "
                    f"name={v('name')!r} brand={v('brand')!r} price={v('price')!r} spec={v('specification')!r}"
                )
                out.append(f"    sp={v('selling_points')!r} desc({len(res.suggested_description or '')}字)")
            except Exception as e:
                out.append(f"run{r+1} FAILED: {type(e).__name__}: {str(e)[:140]}")
    txt = "\n".join(out)
    open("doubao_extract_result.txt", "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    asyncio.run(main())
