from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def sse_event(event: str, **kwargs: Any) -> str:
    """统一 SSE 事件格式化。所有 SSE 输出都走这一个函数。"""

    payload: dict[str, Any] = {"event": event, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---- 便捷函数 ----

def sse_start(stream_type: str, resource_id: str) -> str:
    """流开始事件，告知类型和资源 ID。"""

    return sse_event("start", type=stream_type, id=resource_id)


def sse_delta(content: str) -> str:
    """文本增量事件（打字机效果）。"""

    return sse_event("delta", content=content)


def sse_progress(percent: int, message: str) -> str:
    """进度更新事件（百分比+文案）。"""

    return sse_event("progress", percent=percent, message=message)


def sse_result(data: dict[str, Any]) -> str:
    """完整结构化结果事件。"""

    return sse_event("result", data=data)


def sse_meta(
    *,
    message_id: str | None = None,
    token_input: int = 0,
    token_output: int = 0,
    cost_yuan: float = 0.0,
) -> str:
    """元信息事件（token 用量 / 费用 / 消息 ID）。"""

    return sse_event(
        "meta",
        message_id=message_id,
        tokens={"input": token_input, "output": token_output},
        cost_yuan=cost_yuan,
    )


def sse_error(code: str, message: str) -> str:
    """错误事件。"""

    return sse_event("error", code=code, message=message)


def sse_done() -> str:
    """流结束事件。"""

    return sse_event("done")


# ---- Mock 辅助工具 ----

def split_chinese_chunks(text: str, chunk_size: int = 15) -> list[str]:
    """Split text into short chunks for streaming."""

    chunks: list[str] = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i : i + chunk_size])
    return chunks


async def mock_sse_stream(
    *,
    chunks: list[str],
    message_id: str,
    token_input: int,
    token_output: int,
    cost_yuan: float,
) -> AsyncIterator[str]:
    """Yield SSE events for a mock streaming response."""

    for chunk in chunks:
        yield sse_delta(chunk)
    yield sse_meta(
        message_id=message_id,
        token_input=token_input,
        token_output=token_output,
        cost_yuan=cost_yuan,
    )
    yield sse_done()
