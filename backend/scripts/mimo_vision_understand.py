"""Quick check: does the model understand OBJECTS/scene, not just OCR text."""
from __future__ import annotations

import asyncio
import base64
import os

import httpx

BASE_URL = os.environ["PROBE_BASE"]
MODEL = os.environ["PROBE_MODEL"]
KEY = os.environ["PROBE_KEY"]
IMG = "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551395237897_product_1781140476353.jpg"

ASK = (
    "请分两部分回答：\n"
    "1）【画面物体】图片里有哪些实物/物体？它们长什么样（颜色、形状、材质、包装）？不要读文字，只描述你看到的画面。\n"
    "2）【这是什么】综合判断这是什么产品、什么使用场景。"
)


import time


async def _run(client, b64, thinking_type):
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": ASK},
                ],
            }
        ],
        "stream": False,
        "thinking": {"type": thinking_type},
    }
    t = time.perf_counter()
    resp = await client.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {KEY}"},
        json=payload,
        timeout=180,
    )
    dt = time.perf_counter() - t
    if resp.status_code != 200:
        return dt, f"HTTP {resp.status_code}: {resp.text[:200]}"
    return dt, resp.json()["choices"][0]["message"]["content"]


async def main() -> None:
    async with httpx.AsyncClient() as client:
        r = await client.get(IMG, timeout=30)
        b64 = base64.b64encode(r.content).decode()
        out = []
        for tt in ("disabled", "enabled"):
            dt, content = await _run(client, b64, tt)
            out.append(f"\n{'='*60}\nthinking={tt}  耗时={dt:.1f}s\n{'='*60}\n{content}")
        txt = "\n".join(out)
        open("understand_result.txt", "w", encoding="utf-8").write(txt)
        print(txt)


if __name__ == "__main__":
    asyncio.run(main())
