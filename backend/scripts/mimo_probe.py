"""Probe Xiaomi MiMo-V2.5 multimodal: extraction quality + concurrency ceiling.

Key is read from env MIMO_KEY (never hardcoded). Usage:
    MIMO_KEY=sk-... python scripts/mimo_probe.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time

import httpx

BASE_URL = os.environ.get("PROBE_BASE", "https://api.xiaomimimo.com/v1")
MODEL = os.environ.get("PROBE_MODEL", "mimo-v2.5")
KEY = os.environ.get("PROBE_KEY") or os.environ["MIMO_KEY"]

IMAGES = [
    "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551395237897_product_1781140476353.jpg",
    "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551711604748_product_1781140553313.jpg",
]

SYSTEM = "你是产品信息提取助手。只输出JSON，不要任何多余文字。"
USER = (
    "提取图片中的产品信息，输出JSON：\n"
    '{"name":"","brand":"","category":"","price":"到手价/券后价数字",'
    '"specification":"","selling_points":["最多4条"],"raw_text":"图上所有可见文字"}\n'
    "price 要真实成交价，不要直播间诱饵价。识别不到的填null。"
)


async def _b64(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=30)
    r.raise_for_status()
    return base64.b64encode(r.content).decode()


def _payload(b64img: str) -> dict:
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64img}"}},
                    {"type": "text", "text": USER},
                ],
            },
        ],
        "stream": False,
    }


async def _call(client: httpx.AsyncClient, b64img: str) -> tuple[int, float, str]:
    t = time.perf_counter()
    try:
        r = await client.post(
            f"{BASE_URL}/chat/completions",
            json=_payload(b64img),
            headers={"Authorization": f"Bearer {KEY}"},
            timeout=120,
        )
        dt = time.perf_counter() - t
        if r.status_code != 200:
            return r.status_code, dt, r.text[:160]
        content = r.json()["choices"][0]["message"]["content"]
        return 200, dt, content
    except Exception as e:  # noqa: BLE001
        return -1, time.perf_counter() - t, f"{type(e).__name__}: {str(e)[:120]}"


def _parse(content: str) -> dict:
    c = content.strip()
    if c.startswith("```"):
        c = c.split("```", 2)[1]
        if c.startswith("json"):
            c = c[4:]
        c = c.strip()
    try:
        return json.loads(c)
    except Exception:  # noqa: BLE001
        return {}


async def main() -> None:
    out: list[str] = []
    async with httpx.AsyncClient() as client:
        # ---- Phase 1: quality on both images ----
        out.append("===== 质量测试 =====")
        b64s = [await _b64(client, u) for u in IMAGES]
        for i, b in enumerate(b64s):
            code, dt, content = await _call(client, b)
            if code == 200:
                d = _parse(content)
                out.append(
                    f"img{i+1} {dt:5.1f}s name={d.get('name')!r} brand={d.get('brand')!r} "
                    f"price={d.get('price')!r} spec={d.get('specification')!r}"
                )
                out.append(f"     sp={d.get('selling_points')!r} raw_len={len(str(d.get('raw_text','')))}")
            else:
                out.append(f"img{i+1} {dt:5.1f}s HTTP={code} {content}")

        # ---- Phase 2: concurrency ramp ----
        out.append("\n===== 并发测试 (同一张图，N路齐发) =====")
        b = b64s[0]
        for n in (5, 10, 20):
            t0 = time.perf_counter()
            results = await asyncio.gather(*[_call(client, b) for _ in range(n)])
            wall = time.perf_counter() - t0
            ok = sum(1 for c, _, _ in results if c == 200)
            r429 = sum(1 for c, _, _ in results if c == 429)
            other = [(c, m[:60]) for c, _, m in results if c not in (200, 429)]
            lats = [d for c, d, _ in results if c == 200]
            avg = sum(lats) / len(lats) if lats else 0
            out.append(
                f"N={n:2d}  ok={ok} 429={r429} other={len(other)}  "
                f"墙钟={wall:5.1f}s 成功均延={avg:5.1f}s"
            )
            if other:
                out.append(f"      非200/429样本: {other[:3]}")
            if r429 or other:
                out.append("      → 触到上限，停止加压")
                break
            await asyncio.sleep(2)
    txt = "\n".join(out)
    open("mimo_result.txt", "w", encoding="utf-8").write(txt)
    print(txt)


if __name__ == "__main__":
    asyncio.run(main())
