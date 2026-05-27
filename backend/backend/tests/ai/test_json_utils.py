from __future__ import annotations

import pytest

from app.ai.exceptions import AIResponseInvalid
from app.ai.json_utils import extract_json_object, parse_json_response, validate_required_keys


def test_extract_from_fenced_block() -> None:
    text = '```json\n{"key": "value"}\n```'
    raw = extract_json_object(text)
    assert raw == '{"key": "value"}'


def test_extract_from_plain_text() -> None:
    text = 'Some preamble {"answer": 42} trailing text'
    raw = extract_json_object(text)
    assert '"answer": 42' in raw


def test_extract_raises_when_no_json() -> None:
    with pytest.raises(AIResponseInvalid):
        extract_json_object("No JSON here at all.")


def test_parse_json_response_returns_dict() -> None:
    text = '{"overall_intent": 4, "sentiment": "positive"}'
    result = parse_json_response(text)
    assert result["overall_intent"] == 4
    assert result["sentiment"] == "positive"


def test_parse_json_response_handles_fenced_block() -> None:
    text = "Here is the result:\n```json\n{\"score\": 5}\n```\n"
    result = parse_json_response(text)
    assert result["score"] == 5


def test_parse_json_response_raises_on_invalid_json() -> None:
    with pytest.raises(AIResponseInvalid):
        parse_json_response("{not valid json}")


def test_validate_required_keys_passes_when_present() -> None:
    data: dict[str, object] = {"a": 1, "b": 2, "c": 3}
    validate_required_keys(data, ["a", "b"])  # no exception


def test_validate_required_keys_raises_on_missing() -> None:
    data: dict[str, object] = {"a": 1}
    with pytest.raises(AIResponseInvalid) as exc_info:
        validate_required_keys(data, ["a", "b", "c"])
    assert "b" in str(exc_info.value)
    assert "c" in str(exc_info.value)
