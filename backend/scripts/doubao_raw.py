"""Capture doubao mini's RAW response to the production extract prompt."""
from __future__ import annotations

import asyncio
import base64

import httpx

from app.ai.prompts.product_image_extract import render_prompt
from app.ai.vision_client import ALL_KNOWN_FIELDS

KEY = "ark-33f7289d-08dc-4d4d-a447-ab27c677b384-9ad83"
BASE = "https://ark.cn-beijing.volces.com/api/v3"
MODEL = "doubao-seed-2-0-lite-260428"
IMG = "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551395237897_product_1781140476353.jpg"


import json
import time


def _count(content: str) -> str:
    c = content.strip()
    if c.startswith("```"):
        c = c.split("```", 2)[1]
        c = c[4:] if c.startswith("json") else c
        c = c.strip()
    try:
        d = json.loads(c)
        f = d.get("fields", {})
        filled = sum(1 for k in ALL_KNOWN_FIELDS if isinstance(f.get(k), dict) and f[k].get("value") not in (None, "", []))
        price = f.get("price", {}).get("value") if isinstance(f.get("price"), dict) else None
        return f"filled={filled}/9 price={price!r}"
    except Exception as e:  # noqa: BLE001
        return f"PARSE-FAIL: {str(e)[:50]} | head={c[:60]!r}"


async def main() -> None:
    system = render_prompt(target_fields=ALL_KNOWN_FIELDS, locale="zh")
    user = "请仔细分析图片中的产品，提取所有可见的产品信息，严格按要求输出 JSON。"
    async with httpx.AsyncClient() as c:
        r = await c.get(IMG, timeout=30)
        b64 = base64.b64encode(r.content).decode()
        for i in range(3):
            t = time.perf_counter()
            resp = await c.post(
                f"{BASE}/chat/completions",
                headers={"Authorization": f"Bearer {KEY}"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": user},
                        ]},
                    ],
                    "stream": False,
                    "thinking": {"type": "disabled"},
                },
                timeout=120,
            )
            dt = time.perf_counter() - t
            content = resp.json()["choices"][0]["message"]["content"]
            print(f"run{i+1} {dt:.1f}s {_count(content)}")


if __name__ == "__main__":
    asyncio.run(main())
