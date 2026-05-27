from __future__ import annotations

import json
import re

from app.ai.exceptions import AIResponseInvalid

# Strip markdown fences (```json ... ``` or ``` ... ```)
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


def _find_first_json_block(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced {…} or […] block in text, or None."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json_object(text: str) -> str:
    """Extract the first JSON object/array from fenced code blocks or plain text.

    Strips markdown fences first, then uses bracket-matching so that a response
    containing nested JSON (e.g. 30-question survey) is correctly extracted
    without the lazy-regex truncation bug.
    """

    # 1. Strip markdown fences — then bracket-match the content inside
    fence_match = _FENCE_RE.search(text.strip())
    if fence_match:
        inner = fence_match.group(1).strip()
        block = _find_first_json_block(inner, "{", "}")
        if block is not None:
            return block
        block = _find_first_json_block(inner, "[", "]")
        if block is not None:
            return block

    # 2. No fences — bracket-match the whole text directly
    block = _find_first_json_block(text, "{", "}")
    if block is not None:
        return block

    block = _find_first_json_block(text, "[", "]")
    if block is not None:
        return block

    raise AIResponseInvalid(f"No JSON object found in response: {text[:200]!r}")


def parse_json_response(text: str) -> dict[str, object]:
    """Extract and parse a JSON object from an AI response."""

    raw = extract_json_object(text)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIResponseInvalid(
            f"JSON parse failed: {exc}. Input: {raw[:200]!r}"
        ) from exc

    if not isinstance(result, dict):
        raise AIResponseInvalid(f"Expected JSON object, got {type(result).__name__}")
    return result


def validate_required_keys(data: dict[str, object], keys: list[str]) -> None:
    """Raise AIResponseInvalid if any required key is missing."""

    missing = [k for k in keys if k not in data]
    if missing:
        raise AIResponseInvalid(f"Missing required keys in response: {missing}")
