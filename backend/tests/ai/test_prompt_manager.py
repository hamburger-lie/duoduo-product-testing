from __future__ import annotations

import pytest

from app.ai.exceptions import AIPromptNotFound, AIPromptRenderFailed
from app.ai.prompt_manager import render_prompt


def test_render_product_understand_returns_tuple() -> None:
    rendered, name, versioned = render_prompt(
        "product_understand",
        user_role_type="manufacturer",
        product={"id": 1, "name": "Test Cream", "price": 99},
    )
    assert isinstance(rendered, str)
    assert len(rendered) > 50
    assert name == "product_understand"
    assert versioned.startswith("product_understand@v")


def test_render_persona_chat_includes_context() -> None:
    rendered, _, _ = render_prompt(
        "persona_chat",
        persona={"id": 1, "name": "小红"},
        product_ai_summary={"name": "面霜"},
        persona_answer_history={"overall_intent": 4},
        conversation_history=[{"role": "user", "content": "你好"}],
        user_message="为什么你给了4分？",
    )
    assert "小红" in rendered
    assert "面霜" in rendered
    assert "为什么你给了4分？" in rendered


def test_render_unknown_template_raises_not_found() -> None:
    with pytest.raises(AIPromptNotFound):
        render_prompt("nonexistent_template", foo="bar")


def test_render_missing_variable_raises_render_failed() -> None:
    with pytest.raises(AIPromptRenderFailed):
        # product_understand requires user_role_type and product
        render_prompt("product_understand")


def test_versioned_name_format() -> None:
    _, _, versioned = render_prompt(
        "product_understand",
        user_role_type="channel",
        product={"id": 2, "name": "Serum"},
    )
    import re

    assert re.match(r"product_understand@v\d+\.\d+\.\d+$", versioned)
