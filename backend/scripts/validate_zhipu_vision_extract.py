"""手动验证智谱 GLM-4V 图片字段提取管道。

用法：
    # 使用默认测试图片
    uv run python scripts/validate_zhipu_vision_extract.py

    # 使用自定义图片 URL
    uv run python scripts/validate_zhipu_vision_extract.py https://your-image-url.jpg

前提：
    - .env 中配置 ZHIPU_API_KEY
    - VISION_PROVIDER=zhipu（或 AI_PROVIDER=deepseek 且有 ZHIPU_API_KEY）
    - 图片 URL 必须公网可访问

不要在 pytest 里运行此脚本。
"""

from __future__ import annotations

import asyncio
import json
import sys


def _fix_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main() -> None:
    _fix_stdout()

    from app.ai.vision_client import get_vision_extract_client
    from app.core.config import get_settings

    settings = get_settings()

    # Resolve provider
    provider = settings.vision_provider.strip().lower() or settings.ai_provider.strip().lower()
    print(f"VISION_PROVIDER={settings.vision_provider!r}  AI_PROVIDER={settings.ai_provider!r}")
    print(f"Resolved provider: {provider}")
    print(f"ZHIPU_API_KEY: {'***' + settings.zhipu_api_key[-4:] if settings.zhipu_api_key else '(not set)'}")
    print(f"ZHIPU_MODEL_VISION: {settings.zhipu_model_vision}")
    print()

    # Get image URL from args or use default
    if len(sys.argv) > 1:
        image_url = sys.argv[1]
    else:
        # 珀莱雅官方产品图（公网可访问）
        image_url = (
            "https://img.alicdn.com/imgextra/i1/2217044706499/"
            "O1CN01rBJqPn1ZQhAqYY6AE_!!2217044706499.jpg"
        )

    print(f"Image URL: {image_url}")
    print("=" * 60)

    try:
        client = get_vision_extract_client()
        print(f"Client type: {type(client).__name__}")
        print()

        result = await client.extract_fields(
            image_urls=[image_url],
            target_fields=[],  # all known fields
            locale="zh-CN",
        )

        print("--- raw_text ---")
        print(result.raw_text or "(empty)")
        print()

        print("--- fields ---")
        for name, field in result.fields.items():
            conf_bar = "█" * int(field.confidence * 10)
            print(f"  {name:20s} │ {conf_bar:10s} {field.confidence:.2f} │ {field.value}")
        print()

        print("--- suggested_description ---")
        print(result.suggested_description or "(empty)")
        print()

        print(f"source_image_count: {result.source_image_count}")
        print()
        print("--- Full JSON ---")
        output = {
            "raw_text": result.raw_text,
            "suggested_description": result.suggested_description,
            "source_image_count": result.source_image_count,
            "fields": {
                k: {"value": v.value, "confidence": v.confidence, "source": v.source}
                for k, v in result.fields.items()
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(f"\n[ERROR] {type(exc).__name__}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
