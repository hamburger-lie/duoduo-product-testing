from __future__ import annotations


class AIError(Exception):
    """Base class for AI service errors."""

    code: str = "AI_ERROR"


class AIServiceUnavailable(AIError):
    code = "AI_SERVICE_UNAVAILABLE"


class AIServiceTimeout(AIError):
    code = "AI_SERVICE_TIMEOUT"


class AIRateLimited(AIError):
    code = "AI_RATE_LIMITED"


class AIContentBlocked(AIError):
    code = "AI_CONTENT_BLOCKED"


class AIResponseInvalid(AIError):
    code = "AI_RESPONSE_INVALID"


class AIPromptNotFound(AIError):
    code = "AI_PROMPT_NOT_FOUND"


class AIPromptRenderFailed(AIError):
    code = "AI_PROMPT_RENDER_FAILED"
