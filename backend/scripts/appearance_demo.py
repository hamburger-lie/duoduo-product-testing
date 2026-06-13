import asyncio, base64, json, httpx

KEY = "ark-33f7289d-08dc-4d4d-a447-ab27c677b384-9ad83"
BASE = "https://ark.cn-beijing.volces.com/api/v3"
MODEL = "doubao-seed-2-0-mini-260428"
IMG = "https://cpg.cibe.cn/api/v1/internal/product-images/products/2026/06/7295551395237897_product_1781140476353.jpg"

SYS = (
    "你是产品信息提取助手。分析图片，只输出扁平JSON：\n"
    '{"name":"","brand":"","price":"到手价数字",'
    '"appearance":"用视觉描述产品实物外观——瓶型/容器形状、颜色、材质、质地，不要读文字",'
    '"package_style":"包装设计风格给人的整体感觉"}\n'
    "只输出JSON。"
)


async def main():
    async with httpx.AsyncClient() as c:
        r = await c.get(IMG, timeout=30)
        b64 = base64.b64encode(r.content).decode()
        resp = await c.post(
            f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {KEY}"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYS},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": "提取信息"},
                    ]},
                ],
                "stream": False,
                "thinking": {"type": "disabled"},
            },
            timeout=60,
        )
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            content = content[4:] if content.startswith("json") else content
        d = json.loads(content.strip())
        print(json.dumps(d, ensure_ascii=False, indent=2))


asyncio.run(main())
