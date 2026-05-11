from __future__ import annotations

import json
import re

from app.ai.exceptions import AIResponseInvalid

_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
    re.DOTALL,
)


def extract_json_object(text: str) -> str:
    """Extract a JSON object/array from fenced code blocks or plain text."""

    match = _FENCED_JSON_RE.search(text)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        return text[start : end + 1]

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and start < end:
        return text[start : end + 1]

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
