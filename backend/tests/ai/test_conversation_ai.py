from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest

from app.ai.client import MockAIClient
from app.ai.streaming import sse_error  # noqa: F401 — used in tests

# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------

class _StreamingAIClient(MockAIClient):
    """MockAIClient that streams Chinese text chunks."""

    def __init__(self, text: str = "我觉得这款面霜质地很好，保湿效果不错。") -> None:
        self._text = text

    async def stream(
        self, *, system: str, user: str, endpoint_id: str
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncGenerator[str, None]:
            for i in range(0, len(self._text), 5):
                yield self._text[i : i + 5]

        return _gen()


class _ErrorAIClient(MockAIClient):
    """MockAIClient that raises during streaming."""

    def __init__(self, exc_class: type[Exception] | None = None, msg: str = "boom") -> None:
        self._exc_class = exc_class
        self._msg = msg

    async def stream(
        self, *, system: str, user: str, endpoint_id: str
    ) -> AsyncIterator[str]:
        from app.ai.exceptions import AIServiceTimeout

        exc_cls = self._exc_class or AIServiceTimeout

        async def _gen() -> AsyncGenerator[str, None]:
            raise exc_cls(self._msg)
            yield ""  # type: ignore[misc]  # noqa: E501 — unreachable, required for generator

        return _gen()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _ArkSettings:
    ai_provider = "ark"
    ark_api_key = "sk-test"
    ark_base_url = "https://ark.cn-beijing.volces.com/api/v3"
    ark_ep_doubao_seed_16 = "ep-seed"
    ark_ep_doubao_15_pro_character = "ep-pro"
    ark_ep_doubao_15_lite = "ep-lite"
    ark_ep_vision_pro = "ep-vision"
    ark_ep_embedding = "ep-embed"


class _MockSettings:
    ai_provider = "mock"
    ark_api_key = ""
    ark_base_url = "https://ark.cn-beijing.volces.com/api/v3"
    ark_ep_doubao_seed_16 = ""
    ark_ep_doubao_15_pro_character = ""
    ark_ep_doubao_15_lite = ""
    ark_ep_vision_pro = ""
    ark_ep_embedding = ""


def _fake_conversation() -> Any:
    class _C:
        id = 1
        evaluation_id = 10
        persona_id = 20
        message_count = 2
        last_message_at = None

    return _C()


def _fake_persona() -> Any:
    class _P:
        id = 20
        name = "林雪"
        age = 28
        city = "上海"
        occupation = "产品经理"
        persona_tag = "成分党"
        profile: dict[str, object] = {"bio": "关注成分"}
        avatar = "person"
        owner_id = None

    return _P()


def _fake_product() -> Any:
    class _Pr:
        id = 100
        name = "测试面霜"
        description = "温和保湿面霜"
        category = "护肤"
        brand = "TestBrand"
        price = None
        ai_summary: dict[str, object] | None = None

    return _Pr()


def _fake_evaluation() -> Any:
    class _E:
        id = 10
        product_id = 100

    return _E()


def _fake_answer() -> Any:
    class _A:
        id = 30
        overall_intent = 4
        sentiment = "positive"
        answers: list[dict[str, object]] = [
            {"qid": "q01", "answer": 4, "reason": "质地不错"}
        ]

    return _A()


def _fake_message(role: str, content: str) -> Any:
    from datetime import UTC, datetime

    class _M:
        pass

    m = _M()
    m.id = 999
    m.role = role
    m.content = content
    m.created_at = datetime.now(UTC)
    return m


# ---------------------------------------------------------------------------
# Unit tests: sse_error
# ---------------------------------------------------------------------------

def test_sse_error_format() -> None:
    result = sse_error("AI_SERVICE_TIMEOUT", "Request timed out")
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    parsed = json.loads(result[6:].strip())
    assert parsed["event"] == "error"
    assert parsed["code"] == "AI_SERVICE_TIMEOUT"
    assert parsed["message"] == "Request timed out"


# ---------------------------------------------------------------------------
# Unit tests: _load_chat_context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_chat_context_returns_all_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(
            self, *, evaluation_id: int, persona_id: int
        ) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, *, conversation_id: int) -> int:
            return 4

        async def list_by_conversation_id(
            self, *, conversation_id: int, offset: int, limit: int
        ) -> list[Any]:
            return [
                _fake_message("user", "你好"),
                _fake_message("assistant", "你好，我是林雪。"),
            ]

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]

    ctx = await svc._load_chat_context(_fake_conversation())

    assert "persona" in ctx
    assert ctx["persona"]["name"] == "林雪"
    assert "product_ai_summary" in ctx
    assert ctx["product_ai_summary"]["name"] == "测试面霜"
    assert "persona_answer_history" in ctx
    assert len(ctx["persona_answer_history"]) == 1
    assert ctx["persona_answer_history"][0]["overall_intent"] == 4
    assert "conversation_history" in ctx
    assert len(ctx["conversation_history"]) == 2


@pytest.mark.asyncio
async def test_load_chat_context_limits_to_10_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    captured_args: dict[str, Any] = {}

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(
            self, *, evaluation_id: int, persona_id: int
        ) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, *, conversation_id: int) -> int:
            return 24

        async def list_by_conversation_id(
            self, *, conversation_id: int, offset: int, limit: int
        ) -> list[Any]:
            captured_args["offset"] = offset
            captured_args["limit"] = limit
            return []

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]

    await svc._load_chat_context(_fake_conversation())

    assert captured_args["offset"] == 14  # 24 - 10
    assert captured_args["limit"] == 10


@pytest.mark.asyncio
async def test_load_chat_context_handles_missing_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)

    class _Empty:
        async def get_active_by_id(self, **kw: Any) -> None:
            return None

        async def get_by_id(self, *a: Any, **kw: Any) -> None:
            return None

        async def get_by_evaluation_and_persona(self, **kw: Any) -> None:
            return None

        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

    svc.personas = _Empty()  # type: ignore[assignment]
    svc.evaluations = _Empty()  # type: ignore[assignment]
    svc.products = _Empty()  # type: ignore[assignment]
    svc.answers = _Empty()  # type: ignore[assignment]
    svc.messages = _Empty()  # type: ignore[assignment]

    ctx = await svc._load_chat_context(_fake_conversation())

    assert ctx["persona"] == {}
    assert ctx["product_ai_summary"] == {}
    assert ctx["persona_answer_history"] == []
    assert ctx["conversation_history"] == []


# ---------------------------------------------------------------------------
# Unit tests: _stream_ark_reply
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_ark_reply_yields_delta_meta_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = _StreamingAIClient("你好世界")

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message("assistant", data["content"])

    class _FakeSession:
        async def commit(self) -> None:
            pass

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    conv = _fake_conversation()
    stream = await svc._stream_ark_reply(conversation=conv, user_content="测试")

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert '"event": "delta"' in all_text or '"event":"delta"' in all_text
    assert '"event": "meta"' in all_text or '"event":"meta"' in all_text
    assert '"event": "done"' in all_text or '"event":"done"' in all_text


@pytest.mark.asyncio
async def test_stream_ark_reply_saves_assistant_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    reply_text = "这个面霜保湿效果很好"
    svc._ai_client = _StreamingAIClient(reply_text)

    saved: list[dict[str, Any]] = []

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            saved.append(data)
            return _fake_message("assistant", data.get("content", ""))

    class _FakeSession:
        async def commit(self) -> None:
            pass

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    conv = _fake_conversation()
    stream = await svc._stream_ark_reply(conversation=conv, user_content="测试")
    async for _ in stream:
        pass

    assert len(saved) == 1
    assert saved[0]["role"] == "assistant"
    assert saved[0]["content"] == reply_text
    assert saved[0]["token_input"] is not None
    assert saved[0]["token_output"] is not None


@pytest.mark.asyncio
async def test_stream_ark_reply_error_yields_sse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.exceptions import AIServiceTimeout
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = _ErrorAIClient(AIServiceTimeout, "timed out")

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message("assistant", "")

    class _FakeSession:
        async def commit(self) -> None:
            pass

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    conv = _fake_conversation()
    stream = await svc._stream_ark_reply(conversation=conv, user_content="测试")

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert '"event": "error"' in all_text or '"event":"error"' in all_text
    assert "AI_SERVICE_TIMEOUT" in all_text
    assert '"event": "done"' in all_text or '"event":"done"' in all_text


@pytest.mark.asyncio
async def test_stream_ark_reply_unexpected_error_yields_generic_sse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = _ErrorAIClient(RuntimeError, "unexpected")

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message("assistant", "")

    class _FakeSession:
        async def commit(self) -> None:
            pass

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    conv = _fake_conversation()
    stream = await svc._stream_ark_reply(conversation=conv, user_content="测试")

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert "AI_ERROR" in all_text


# ---------------------------------------------------------------------------
# Unit tests: send_message routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_message_mock_path_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ai_provider=mock, send_message uses the mock path (no AI client)."""
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _MockSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = None

    class _Conv:
        id = 1
        evaluation_id = 10
        persona_id = 20
        message_count = 0
        last_message_at = None
        user_id = 1

    class _Conversations:
        async def get_by_id_and_user_id(self, **kw: Any) -> Any:
            return _Conv()

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message(data.get("role", "user"), data.get("content", ""))

    class _FakeSession:
        async def flush(self) -> None:
            pass

        async def commit(self) -> None:
            pass

    class _FakeUser:
        id = 1

    svc.conversations = _Conversations()  # type: ignore[assignment]
    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    stream = await svc.send_message(
        user=_FakeUser(),  # type: ignore[arg-type]
        conversation_id=1,
        content="你好",
    )

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert '"event": "delta"' in all_text or '"event":"delta"' in all_text
    assert '"event": "done"' in all_text or '"event":"done"' in all_text


@pytest.mark.asyncio
async def test_send_message_ark_path_routes_to_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ai_provider=ark, send_message uses the ark streaming path."""
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = _StreamingAIClient("测试回复")

    class _Conv:
        id = 1
        evaluation_id = 10
        persona_id = 20
        message_count = 0
        last_message_at = None
        user_id = 1

    class _Conversations:
        async def get_by_id_and_user_id(self, **kw: Any) -> Any:
            return _Conv()

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message(data.get("role", "user"), data.get("content", ""))

    class _FakeSession:
        async def flush(self) -> None:
            pass

        async def commit(self) -> None:
            pass

    class _FakeUser:
        id = 1

    svc.conversations = _Conversations()  # type: ignore[assignment]
    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    stream = await svc.send_message(
        user=_FakeUser(),  # type: ignore[arg-type]
        conversation_id=1,
        content="你好",
    )

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert "测试回复" in all_text
    assert '"event": "delta"' in all_text or '"event":"delta"' in all_text
    assert '"event": "meta"' in all_text or '"event":"meta"' in all_text
    assert '"event": "done"' in all_text or '"event":"done"' in all_text


# ---------------------------------------------------------------------------
# Prompt template tests
# ---------------------------------------------------------------------------

def test_persona_chat_template_renders_without_memory() -> None:
    from app.ai.prompt_manager import render_prompt

    rendered, name, _ = render_prompt(
        "persona_chat",
        persona={"name": "林雪", "age": 28},
        product_ai_summary={"name": "面霜"},
        persona_answer_history=[{"overall_intent": 4}],
        conversation_history=[{"role": "user", "content": "你好"}],
        user_message="你觉得这个产品怎么样？",
    )
    assert "林雪" in rendered
    assert "面霜" in rendered
    assert "你觉得这个产品怎么样？" in rendered
    assert name == "persona_chat"


def test_persona_chat_template_contains_safety_rules() -> None:
    from app.ai.prompt_manager import render_prompt

    rendered, _, _ = render_prompt(
        "persona_chat",
        persona={},
        product_ai_summary={},
        persona_answer_history=[],
        conversation_history=[],
        user_message="test",
    )
    assert "不准承认自己是 AI" in rendered
    assert "第一人称" in rendered


def test_persona_chat_template_no_memory_context_section() -> None:
    """Removed memory_context from template — verify no Jinja error."""
    from app.ai.prompt_manager import render_prompt

    rendered, _, _ = render_prompt(
        "persona_chat",
        persona={},
        product_ai_summary={},
        persona_answer_history=[],
        conversation_history=[],
        user_message="test",
    )
    assert len(rendered) > 0


# ---------------------------------------------------------------------------
# Rate-limited / unavailable error mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_ark_reply_rate_limited_yields_correct_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.exceptions import AIRateLimited
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = _ErrorAIClient(AIRateLimited, "rate limited")

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message("assistant", "")

    class _FakeSession:
        async def commit(self) -> None:
            pass

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    conv = _fake_conversation()
    stream = await svc._stream_ark_reply(conversation=conv, user_content="测试")

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert "AI_RATE_LIMITED" in all_text


@pytest.mark.asyncio
async def test_stream_ark_reply_service_unavailable_yields_correct_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.exceptions import AIServiceUnavailable
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ArkSettings())

    from app.services.conversation_service import ConversationService

    svc = ConversationService.__new__(ConversationService)
    svc._ai_client = _ErrorAIClient(AIServiceUnavailable, "service down")

    class _Personas:
        async def get_active_by_id(self, *, persona_id: int) -> Any:
            return _fake_persona()

    class _Evals:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_evaluation()

    class _Products:
        async def get_by_id(self, entity_id: int, include_deleted: bool = False) -> Any:
            return _fake_product()

    class _Answers:
        async def get_by_evaluation_and_persona(self, **kw: Any) -> Any:
            return _fake_answer()

    class _Messages:
        async def count_by_conversation_id(self, **kw: Any) -> int:
            return 0

        async def list_by_conversation_id(self, **kw: Any) -> list[Any]:
            return []

        async def create(self, data: dict[str, Any]) -> Any:
            return _fake_message("assistant", "")

    class _FakeSession:
        async def commit(self) -> None:
            pass

    svc.personas = _Personas()  # type: ignore[assignment]
    svc.evaluations = _Evals()  # type: ignore[assignment]
    svc.products = _Products()  # type: ignore[assignment]
    svc.answers = _Answers()  # type: ignore[assignment]
    svc.messages = _Messages()  # type: ignore[assignment]
    svc.session = _FakeSession()  # type: ignore[assignment]

    conv = _fake_conversation()
    stream = await svc._stream_ark_reply(conversation=conv, user_content="测试")

    events: list[str] = []
    async for event in stream:
        events.append(event)

    all_text = "".join(events)
    assert "AI_SERVICE_UNAVAILABLE" in all_text
