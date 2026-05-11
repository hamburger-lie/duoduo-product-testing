from __future__ import annotations

import pytest

from app.ai.exceptions import (
    AIContentBlocked,
    AIError,
    AIPromptNotFound,
    AIPromptRenderFailed,
    AIRateLimited,
    AIResponseInvalid,
    AIServiceTimeout,
    AIServiceUnavailable,
)


def test_all_exceptions_inherit_ai_error() -> None:
    subclasses = [
        AIServiceUnavailable,
        AIServiceTimeout,
        AIRateLimited,
        AIContentBlocked,
        AIResponseInvalid,
        AIPromptNotFound,
        AIPromptRenderFailed,
    ]
    for cls in subclasses:
        assert issubclass(cls, AIError), f"{cls.__name__} must subclass AIError"


def test_exception_codes_are_unique() -> None:
    classes = [
        AIServiceUnavailable,
        AIServiceTimeout,
        AIRateLimited,
        AIContentBlocked,
        AIResponseInvalid,
        AIPromptNotFound,
        AIPromptRenderFailed,
    ]
    codes = [cls.code for cls in classes]
    assert len(codes) == len(set(codes)), "Error codes must be unique"


def test_exceptions_are_catchable_as_ai_error() -> None:
    with pytest.raises(AIError):
        raise AIResponseInvalid("bad response")

    with pytest.raises(AIError):
        raise AIPromptNotFound("missing template")
