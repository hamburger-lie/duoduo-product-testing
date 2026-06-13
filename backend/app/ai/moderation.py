from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.ai.exceptions import AIContentBlocked

logger = logging.getLogger(__name__)

ModerationAction = str
ModerationSource = str

ACTION_ALLOW: ModerationAction = "allow"
ACTION_REVIEW: ModerationAction = "review"
ACTION_BLOCK: ModerationAction = "block"

SOURCE_PRODUCT_INPUT: ModerationSource = "product_input"
SOURCE_CONVERSATION_INPUT: ModerationSource = "conversation_input"
SOURCE_CONVERSATION_OUTPUT: ModerationSource = "conversation_output"
SOURCE_VISION_TEXT: ModerationSource = "vision_text"
SOURCE_AI_OUTPUT: ModerationSource = "ai_output"


@dataclass(frozen=True)
class ModerationRule:
    """One local moderation rule."""

    category: str
    severity: str
    action: ModerationAction
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class ModerationResult:
    """Structured result for a local moderation scan."""

    action: ModerationAction
    category: str | None = None
    severity: str | None = None
    snippet: str | None = None

    @property
    def needs_review(self) -> bool:
        """Return whether callers should mark the content for review."""

        return self.action == ACTION_REVIEW


_RULES = [
    ModerationRule(
        category="self_harm",
        severity="high",
        action=ACTION_BLOCK,
        patterns=(re.compile(r"(自杀|自残|自我伤害)", re.IGNORECASE),),
    ),
    ModerationRule(
        category="illegal",
        severity="high",
        action=ACTION_BLOCK,
        patterns=(
            re.compile(r"(毒品|冰毒|大麻|海洛因)", re.IGNORECASE),
            re.compile(r"(枪支|炸弹|爆炸物)", re.IGNORECASE),
        ),
    ),
    ModerationRule(
        category="adult",
        severity="high",
        action=ACTION_BLOCK,
        patterns=(re.compile(r"(色情|裸体|性交)", re.IGNORECASE),),
    ),
    ModerationRule(
        category="gambling",
        severity="high",
        action=ACTION_BLOCK,
        patterns=(re.compile(r"(赌博|博彩|六合彩)", re.IGNORECASE),),
    ),
    ModerationRule(
        category="political_illegal",
        severity="high",
        action=ACTION_BLOCK,
        patterns=(
            re.compile(
                r"("
                r"危害国家安全|泄露国家秘密|颠覆国家政权|推翻国家制度|"
                r"分裂国家|破坏国家统一|煽动民族仇恨|民族歧视|"
                r"宣扬恐怖主义|宣扬极端主义|散布政治谣言|"
                r"伪造政府公告|伪造官方文件|伪造新闻"
                r")",
                re.IGNORECASE,
            ),
        ),
    ),
    ModerationRule(
        category="political_review",
        severity="medium",
        action=ACTION_REVIEW,
        patterns=(
            re.compile(
                r"(时政|公共事件).{0,20}(生成|撰写|编写).{0,20}(新闻|通知|报道)",
                re.IGNORECASE,
            ),
            re.compile(
                r"(生成|撰写|编写).{0,20}(官方通知|新闻报道|时政|公共事件)",
                re.IGNORECASE,
            ),
        ),
    ),
]


@runtime_checkable
class ModerationAdapter(Protocol):
    """Protocol for content moderation adapters."""

    async def review(
        self,
        text: str,
        *,
        source: ModerationSource,
    ) -> ModerationResult:
        """Return a structured moderation result."""
        ...

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

    async def review(
        self,
        text: str,
        *,
        source: ModerationSource,
    ) -> ModerationResult:
        """Review text and return the source-specific action."""

        return self._review_patterns(text, source=source)

    async def check_input(self, text: str) -> None:
        """Check user input for blocked content."""

        result = await self.review(text, source=SOURCE_PRODUCT_INPUT)
        self._raise_if_blocked(result, direction="input")

    async def check_output(self, text: str) -> None:
        """Check AI output for blocked content."""

        result = await self.review(text, source=SOURCE_AI_OUTPUT)
        self._raise_if_blocked(result, direction="output")

    def _review_patterns(
        self,
        text: str,
        *,
        source: ModerationSource,
    ) -> ModerationResult:
        """Scan text against local moderation rules."""

        if not text.strip():
            return ModerationResult(action=ACTION_ALLOW)

        for rule in _RULES:
            for pattern in rule.patterns:
                match = pattern.search(text)
                if match:
                    action = self._action_for_source(rule, source)
                    return ModerationResult(
                        action=action,
                        category=rule.category,
                        severity=rule.severity,
                        snippet=self._redacted_snippet(match.group()),
                    )
        return ModerationResult(action=ACTION_ALLOW)

    def _action_for_source(
        self,
        rule: ModerationRule,
        source: ModerationSource,
    ) -> ModerationAction:
        """Apply source-specific policy to a matched rule."""

        if source == SOURCE_VISION_TEXT:
            return ACTION_REVIEW
        return rule.action

    def _raise_if_blocked(self, result: ModerationResult, *, direction: str) -> None:
        """Raise the existing exception for blocked content."""

        if result.action != ACTION_BLOCK:
            return
        logger.warning(
            "content_blocked direction=%s category=%s severity=%s snippet=%s",
            direction,
            result.category,
            result.severity,
            result.snippet,
        )
        raise AIContentBlocked("Content blocked: prohibited content detected")

    def _redacted_snippet(self, text: str) -> str:
        """Return a short snippet without logging the exact matched term."""

        if len(text) <= 2:
            return "*" * len(text)
        return f"{text[0]}***{text[-1]}"


class NoopModerationAdapter:
    """Pass-through adapter that never blocks. For testing only."""

    async def review(
        self,
        text: str,
        *,
        source: ModerationSource,
    ) -> ModerationResult:
        """Always allow content."""

        return ModerationResult(action=ACTION_ALLOW)

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
