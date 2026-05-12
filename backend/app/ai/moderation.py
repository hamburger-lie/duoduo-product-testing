from __future__ import annotations

import logging
import re
from typing import Protocol, runtime_checkable

from app.ai.exceptions import AIContentBlocked

logger = logging.getLogger(__name__)

_BLOCKED_PATTERNS = [
    re.compile(r"(自杀|自残|自我伤害)", re.IGNORECASE),
    re.compile(r"(毒品|冰毒|大麻|海洛因)", re.IGNORECASE),
    re.compile(r"(枪支|炸弹|爆炸物)", re.IGNORECASE),
    re.compile(r"(色情|裸体|性交)", re.IGNORECASE),
    re.compile(r"(赌博|博彩|六合彩)", re.IGNORECASE),
]


@runtime_checkable
class ModerationAdapter(Protocol):
    """Protocol for content moderation adapters."""

    async def check_input(self, text: str) -> None:
        """Raise AIContentBlocked if input is rejected."""
        ...

    async def check_output(self, text: str) -> None:
        """Raise AIContentBlocked if output is rejected."""
        ...


class LocalModerationAdapter:
    """Keyword-based local moderation for MVP.

    Production should replace this with a real moderation API
    (e.g., Volcengine content moderation or similar).
    """

    async def check_input(self, text: str) -> None:
        """Check user input for blocked content."""

        self._check_patterns(text, direction="input")

    async def check_output(self, text: str) -> None:
        """Check AI output for blocked content."""

        self._check_patterns(text, direction="output")

    def _check_patterns(self, text: str, *, direction: str) -> None:
        """Scan text against blocked patterns."""

        for pattern in _BLOCKED_PATTERNS:
            match = pattern.search(text)
            if match:
                logger.warning(
                    "content_blocked direction=%s matched=%s",
                    direction,
                    match.group()[:20],
                )
                raise AIContentBlocked(
                    "Content blocked: prohibited content detected"
                )


class NoopModerationAdapter:
    """Pass-through adapter that never blocks. For testing only."""

    async def check_input(self, text: str) -> None:
        """No-op."""

    async def check_output(self, text: str) -> None:
        """No-op."""


def get_moderation_adapter() -> LocalModerationAdapter | NoopModerationAdapter:
    """Return the appropriate moderation adapter based on settings."""

    try:
        from app.core.config import get_settings

        s = get_settings()
        if s.app_env == "test":
            return NoopModerationAdapter()
    except Exception:
        pass
    return LocalModerationAdapter()
