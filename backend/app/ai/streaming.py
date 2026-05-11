from __future__ import annotations

import json
from collections.abc import AsyncIterator


def sse_event(data: dict[str, object]) -> str:
    """Format a single SSE event line."""

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_delta(content: str) -> str:
    """Format a delta event."""

    return sse_event({"event": "delta", "content": content})


def sse_meta(
    *,
    message_id: str,
    token_input: int,
    token_output: int,
    cost_yuan: float,
) -> str:
    """Format a meta event."""

    return sse_event(
        {
            "event": "meta",
            "message_id": message_id,
            "tokens": {"input": token_input, "output": token_output},
            "cost_yuan": cost_yuan,
        }
    )


def sse_error(code: str, message: str) -> str:
    """Format an error event."""

    return sse_event({"event": "error", "code": code, "message": message})


def sse_done() -> str:
    """Format a done event."""

    return sse_event({"event": "done"})


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
