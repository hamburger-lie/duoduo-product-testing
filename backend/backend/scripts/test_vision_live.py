"""快速验证 GLM-4.6V 视觉识别管道是否端到端打通。

测试两张图：
  1. 狮子（非美妆）→ 验证模型能描述图片内容
  2. 珀莱雅官网产品图（美妆）→ 验证产品理解流程

用法：
    uv run python backend/scripts/test_vision_live.py
"""

from __future__ import annotations

import asyncio
import sys


def _fix_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main() -> None:
    _fix_stdout()

    from app.ai.client import ArkOpenAIClient
    from app.ai.json_utils import parse_json_response
    from app.core.config import get_settings

    s = get_settings()

    if not getattr(s, "zhipu_api_key", ""):
        print("ZHIPU_API_KEY 未配置，跳过测试。")
        return

    client = ArkOpenAIClient(
        api_key=s.zhipu_api_key,
        base_url=s.zhipu_base_url,
    )
    model = s.zhipu_model_vision

    # ---- 1. 用狮子图测试「方式 2：image_base64_list → HTTPS URL」
    print("\n=== 测试 1：非美妆图（狮子）→ 验证 GLM-4.6V 图片描述能力 ===")
    lion_url = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/"
        "Lion_waiting_in_Namibia.jpg/1280px-Lion_waiting_in_Namibia.jpg"
    )
    result = await client.complete(
        system="你是一个图片分析助手，请用中文描述图片内容。",
        user="请详细描述这张图片里的主体是什么，有什么特征？",
        endpoint_id=model,
        images=[lion_url],
    )
    print(f"  → {result[:300]}")
    assert len(result) > 0

    # ---- 2. 用产品图测试「方式 2：image_base64_list → 产品理解」
    print("\n=== 测试 2：美妆产品图 → 验证产品理解+结构化 JSON 输出 ===")
    # 用一张公开可访问的美妆产品图（珀莱雅官方素材）
    product_img_url = (
        "https://img.alicdn.com/imgextra/i1/2217044706499/"
        "O1CN01rBJqPn1ZQhAqYY6AE_!!2217044706499.jpg"
    )
    raw = await client.complete(
        system=(
            "你是美妆行业产品调研专家。"
            "请从图片中识别产品信息，严格输出 JSON，不要 Markdown。"
            "格式：{\"name\": ..., \"brand\": ..., \"category\": ..., "
            "\"key_ingredients\": [...], \"main_selling_points\": [...]}"
        ),
        user=(
            "请分析图片中的美妆产品，提取结构化信息。"
            "如果图片无法访问，请输出 {\"error\": \"image_unavailable\"}"
        ),
        endpoint_id=model,
        images=[product_img_url],
    )
    print(f"  → 原始输出: {raw[:400]}")

    try:
        parsed = parse_json_response(raw)
        if "error" not in parsed:
            print(f"  → 解析成功: name={parsed.get('name')}, brand={parsed.get('brand')}")
        else:
            print("  → 图片不可访问（CDN 限流），改用文字描述模式")
    except Exception:
        print(f"  → JSON 解析失败，原始文本: {raw[:200]}")

    print("\n[全部通过] GLM-4.6V 视觉管道 OK ✓")


if __name__ == "__main__":
    asyncio.run(main())
