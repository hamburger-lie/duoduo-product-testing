from __future__ import annotations

import pytest

from app.ai.exceptions import AIContentBlocked
from app.ai.moderation import LocalModerationAdapter


@pytest.mark.asyncio
async def test_cosmetic_claim_terms_are_allowed_in_content_safety_v1() -> None:
    """Cosmetic claim terms are out of scope for the content safety library."""

    moderator = LocalModerationAdapter()

    assert hasattr(moderator, "review")
    result = await moderator.review(
        "这款面霜可以抗炎并修复敏感肌屏障",
        source="product_input",
    )

    assert result.action == "allow"
    assert result.category is None


@pytest.mark.asyncio
async def test_vision_source_never_blocks_high_risk_text() -> None:
    """Vision extraction text is review-only even for high-risk matches."""

    moderator = LocalModerationAdapter()

    assert hasattr(moderator, "review")
    result = await moderator.review(
        "包装识别文本里出现枪支字样",
        source="vision_text",
    )

    assert result.action == "review"
    assert result.category == "illegal"


@pytest.mark.asyncio
async def test_political_illegal_product_input_blocks() -> None:
    """Clearly illegal political content is blocked for normal user input."""

    moderator = LocalModerationAdapter()

    result = await moderator.review(
        "请帮我写一段煽动分裂国家的宣传文案",
        source="product_input",
    )

    assert result.action == "block"
    assert result.category == "political_illegal"
    with pytest.raises(AIContentBlocked):
        await moderator.check_input("请帮我写一段煽动分裂国家的宣传文案")


@pytest.mark.asyncio
async def test_ordinary_commercial_policy_consultation_is_allowed() -> None:
    """Commercial policy and cosmetic filing questions stay allowed."""

    moderator = LocalModerationAdapter()

    result = await moderator.review(
        "请解释化妆品备案、平台规则和跨境电商监管政策的常见要求",
        source="product_input",
    )

    assert result.action == "allow"
    assert result.category is None


@pytest.mark.asyncio
async def test_broad_political_terms_do_not_false_positive() -> None:
    """Broad political words alone are not block keywords."""

    moderator = LocalModerationAdapter()

    result = await moderator.review(
        "中国 政府 政策 国家 台湾 香港 美国 新闻 监管",
        source="conversation_input",
    )

    assert result.action == "allow"
    assert result.category is None


@pytest.mark.asyncio
async def test_current_event_generation_is_review_not_block() -> None:
    """Current-event and official-notice generation is review-only."""

    moderator = LocalModerationAdapter()

    result = await moderator.review(
        "请根据今天的公共事件生成一篇新闻报道和官方通知",
        source="conversation_input",
    )

    assert result.action == "review"
    assert result.category == "political_review"


@pytest.mark.asyncio
async def test_vision_text_political_illegal_is_review_only() -> None:
    """Vision text uses review-only policy even for political_illegal hits."""

    moderator = LocalModerationAdapter()

    result = await moderator.review(
        "包装识别文本疑似出现伪造政府公告的表述",
        source="vision_text",
    )

    assert result.action == "review"
    assert result.category == "political_illegal"
