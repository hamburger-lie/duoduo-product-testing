from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol, runtime_checkable

import httpx

from app.ai.circuit_breaker import CircuitBreaker
from app.ai.exceptions import (
    AIRateLimited,
    AIServiceTimeout,
    AIServiceUnavailable,
)
from app.ai.usage import AITextResult, AIUsage, estimate_cost_yuan
from app.core.metrics import record_ai_request

logger = logging.getLogger(__name__)


@runtime_checkable
class AIClient(Protocol):
    """Protocol for AI completion clients."""

    async def complete(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
    ) -> str: ...

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
        extra_body: dict[str, object] | None = None,
    ) -> str: ...

    async def complete_json_with_usage(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> AITextResult: ...

    async def stream(
        self, *, system: str, user: str, endpoint_id: str
    ) -> AsyncIterator[str]: ...


class MockAIClient:
    """Fully functional mock — no external calls."""

    async def complete(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
    ) -> str:
        img_note = f" (with {len(images)} image(s))" if images else ""
        return f"Mock response for endpoint {endpoint_id}{img_note}."

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
        extra_body: dict[str, object] | None = None,
    ) -> str:
        return f'{{"mock": true, "endpoint_id": "{endpoint_id}"}}'

    async def complete_json_with_usage(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> AITextResult:
        try:
            content = await self.complete_json(
                system=system,
                user=user,
                endpoint_id=endpoint_id,
                images=images,
                max_retries=max_retries,
                max_tokens=max_tokens,
            )
        except TypeError:
            content = await self.complete_json(
                system=system,
                user=user,
                endpoint_id=endpoint_id,
            )
        return AITextResult(content=content, usage=AIUsage())

    async def stream(
        self, *, system: str, user: str, endpoint_id: str
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncGenerator[str, None]:
            yield f"Mock stream chunk 1 for {endpoint_id}."
            yield " Mock stream chunk 2."

        return _gen()


class ArkOpenAIClient:
    """OpenAI-compatible client for LLM APIs (Ark, DeepSeek, etc.).

    All calls use streaming internally to avoid client-side read timeouts.
    Each SSE chunk resets the httpx read timer, preventing client-side
    timeouts even for slow generations.
    """

    _STREAM_TIMEOUT = httpx.Timeout(
        connect=30.0, read=600.0, write=30.0, pool=30.0,
    )
    _MAX_RETRIES = 1
    _METRICS_PROVIDER = "ark"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if api_key and base_url:
            self._api_key = api_key
            self._base_url = base_url.rstrip("/")
        else:
            from app.core.config import get_settings

            s = get_settings()
            self._api_key = s.ark_api_key
            self._base_url = s.ark_base_url.rstrip("/")
        self._circuit_breaker = CircuitBreaker()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _chat_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    @staticmethod
    def _extract_usage(chunk_data: dict[str, object]) -> tuple[int, int, int] | None:
        """Extract provider token usage from one streamed response chunk."""

        usage = chunk_data.get("usage")
        if not isinstance(usage, dict):
            return None
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if (
            not isinstance(prompt_tokens, int)
            or not isinstance(completion_tokens, int)
            or not isinstance(total_tokens, int)
        ):
            return None
        return prompt_tokens, completion_tokens, total_tokens

    @staticmethod
    def _log_usage(endpoint_id: str, usage: tuple[int, int, int]) -> None:
        prompt_tokens, completion_tokens, total_tokens = usage
        logger.info(
            "ai_usage endpoint=%s prompt_tokens=%d completion_tokens=%d total_tokens=%d",
            endpoint_id,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

    @staticmethod
    def _build_messages(
        system: str,
        user: str,
        images: list[str] | None = None,
    ) -> list[dict[str, object]]:
        """Build OpenAI-compatible messages, with optional multimodal image content.

        Each image in ``images`` can be:
        - A raw base64 string (JPEG assumed)
        - A data-URL like ``data:image/png;base64,<...>``
        - An HTTPS URL pointing to an accessible image

        The resulting user content follows the vision multimodal format so
        it works with GLM-4.6V and any OpenAI-compatible vision endpoint.
        """
        if images:
            content: list[dict[str, object]] = []
            for img in images:
                if img.startswith(("http://", "https://")):
                    url_val: str = img
                elif img.startswith("data:"):
                    url_val = img
                else:
                    # Raw base64 — assume JPEG
                    url_val = f"data:image/jpeg;base64,{img}"
                content.append(
                    {"type": "image_url", "image_url": {"url": url_val}}
                )
            content.append({"type": "text", "text": user})
            return [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ]
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _raise_for_status(status_code: int, body: str = "") -> None:
        if status_code == 429:
            logger.warning("ark_rate_limited body=%s", body[:500])
            raise AIRateLimited(f"Ark API rate limited: {body[:200]}")
        if status_code >= 500:
            logger.error("ark_server_error status=%d body=%s", status_code, body[:500])
            raise AIServiceUnavailable(
                f"Ark API server error {status_code}",
            )
        if status_code >= 400:
            logger.error("ark_client_error status=%d body=%s", status_code, body[:500])
            raise AIServiceUnavailable(
                f"Ark API client error {status_code}: {body[:200]}"
            )

    async def _stream_collect_with_usage(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        extra_body: dict[str, object] | None = None,
    ) -> AITextResult:
        """Stream the response and collect content plus token usage.

        Using streaming avoids client-side read timeouts: each SSE chunk
        resets the httpx read timer even if the model takes minutes to
        finish generating.

        When *json_mode* is True, ``response_format: {"type": "json_object"}``
        is added to the request payload so the model is constrained to output
        valid JSON only (supported by DeepSeek / OpenAI-compatible APIs).
        """

        url = self._chat_url()
        headers = self._headers()
        payload: dict[str, object] = {
            "model": endpoint_id,
            "messages": self._build_messages(system, user, images),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if extra_body:
            payload.update(extra_body)

        collected: list[str] = []
        reasoning_collected: list[str] = []
        latest_usage: tuple[int, int, int] | None = None
        async with httpx.AsyncClient(timeout=self._STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    self._raise_for_status(
                        resp.status_code,
                        body.decode("utf-8", errors="replace"),
                    )
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    chunk = line[6:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        chunk_data: dict[str, object] = json.loads(chunk)
                        usage = self._extract_usage(chunk_data)
                        if usage is not None:
                            latest_usage = usage
                            self._log_usage(endpoint_id, usage)
                        choices = chunk_data.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        first = choices[0]
                        if not isinstance(first, dict):
                            continue
                        delta = first.get("delta", {})
                        if not isinstance(delta, dict):
                            continue
                        content = delta.get("content", "")
                        if content:
                            collected.append(str(content))
                        # DeepSeek-v4-flash sometimes emits the full
                        # response inside ``reasoning_content`` instead
                        # of ``content``.  Collect it as a fallback.
                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            reasoning_collected.append(str(reasoning))
                    except (json.JSONDecodeError, KeyError):
                        continue

        result = "".join(collected)
        if not result.strip() and reasoning_collected:
            # Model placed entire output in reasoning_content —
            # fall back so the caller still gets usable text.
            logger.warning(
                "ark_content_in_reasoning endpoint=%s reasoning_len=%d",
                endpoint_id,
                sum(len(c) for c in reasoning_collected),
            )
            result = "".join(reasoning_collected)
        if not result.strip():
            logger.warning(
                "ark_empty_response endpoint=%s", endpoint_id,
            )
            raise AIServiceUnavailable(
                "Ark API returned empty response"
            )
        usage_result = AIUsage()
        if latest_usage is not None:
            from app.core.config import get_settings

            settings = get_settings()
            raw_usage = AIUsage(
                input_tokens=latest_usage[0],
                output_tokens=latest_usage[1],
            )
            usage_result = AIUsage(
                input_tokens=raw_usage.input_tokens,
                output_tokens=raw_usage.output_tokens,
                cost_yuan=estimate_cost_yuan(
                    raw_usage,
                    input_price_per_1k=settings.ai_input_price_yuan_per_1k,
                    output_price_per_1k=settings.ai_output_price_yuan_per_1k,
                ),
            )
        return AITextResult(content=result, usage=usage_result)

    async def _stream_collect(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        extra_body: dict[str, object] | None = None,
    ) -> str:
        """Stream the response and collect all content into a single string."""

        result = await self._stream_collect_with_usage(
            system=system,
            user=user,
            endpoint_id=endpoint_id,
            images=images,
            max_tokens=max_tokens,
            json_mode=json_mode,
            extra_body=extra_body,
        )
        return result.content

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
    ) -> str:
        """Completion via streaming-collect with retry on timeout and 429.

        Pass ``images`` to enable multimodal vision input (base64, data-URL,
        or HTTPS URL). Requires a vision-capable endpoint (e.g. GLM-4.6V).
        """

        started_at = time.monotonic()
        try:
            result = await self._circuit_breaker.call(
                lambda: self._complete(
                    system=system,
                    user=user,
                    endpoint_id=endpoint_id,
                    images=images,
                )
            )
        except Exception:
            record_ai_request(
                self._METRICS_PROVIDER,
                endpoint_id,
                "error",
                time.monotonic() - started_at,
            )
            raise
        record_ai_request(
            self._METRICS_PROVIDER,
            endpoint_id,
            "success",
            time.monotonic() - started_at,
        )
        return result

    async def _complete(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        extra_body: dict[str, object] | None = None,
    ) -> str:
        """Completion implementation without circuit breaker wrapping."""

        max_attempts = 1 + self._MAX_RETRIES
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return await self._stream_collect(
                    system=system, user=user, endpoint_id=endpoint_id,
                    images=images, max_tokens=max_tokens, json_mode=json_mode,
                    extra_body=extra_body,
                )
            except (AIRateLimited, AIServiceUnavailable) as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    wait = 5.0 * (attempt + 1)
                    logger.warning(
                        "ark_transient_retry attempt=%d wait=%.1fs error=%s",
                        attempt + 1,
                        wait,
                        type(exc).__name__,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    wait = 3.0 * (attempt + 1)
                    logger.warning(
                        "ark_complete_timeout_retry attempt=%d wait=%.1fs",
                        attempt + 1,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise AIServiceTimeout(
                    "Ark API timed out after retries"
                ) from exc
            except httpx.RequestError as exc:
                raise AIServiceUnavailable(
                    f"Network error calling Ark API: {exc}"
                ) from exc

        raise AIServiceTimeout("Ark API timed out") from last_exc

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
        extra_body: dict[str, object] | None = None,
    ) -> str:
        """Like complete() but validates the response is parseable JSON.

        Retries up to *max_retries* times when the model returns malformed JSON.
        On each retry the system prompt is reinforced with an explicit JSON-only
        instruction to reduce the chance of another format error.
        """

        started_at = time.monotonic()
        try:
            result = await self._circuit_breaker.call(
                lambda: self._complete_json(
                    system=system,
                    user=user,
                    endpoint_id=endpoint_id,
                    images=images,
                    max_retries=max_retries,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                )
            )
        except Exception:
            record_ai_request(
                self._METRICS_PROVIDER,
                endpoint_id,
                "error",
                time.monotonic() - started_at,
            )
            raise
        record_ai_request(
            self._METRICS_PROVIDER,
            endpoint_id,
            "success",
            time.monotonic() - started_at,
        )
        return result

    async def complete_json_with_usage(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> AITextResult:
        """Like complete_json(), returning provider usage when available."""

        started_at = time.monotonic()
        try:
            result = await self._circuit_breaker.call(
                lambda: self._complete_json_with_usage(
                    system=system,
                    user=user,
                    endpoint_id=endpoint_id,
                    images=images,
                    max_retries=max_retries,
                    max_tokens=max_tokens,
                )
            )
        except Exception:
            record_ai_request(
                self._METRICS_PROVIDER,
                endpoint_id,
                "error",
                time.monotonic() - started_at,
            )
            raise
        record_ai_request(
            self._METRICS_PROVIDER,
            endpoint_id,
            "success",
            time.monotonic() - started_at,
        )
        return result

    async def _complete_json(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
        extra_body: dict[str, object] | None = None,
    ) -> str:
        """JSON completion implementation without circuit breaker wrapping."""

        import logging as _logging

        from app.ai.exceptions import AIResponseInvalid
        from app.ai.json_utils import parse_json_response

        _log = _logging.getLogger(__name__)

        last_exc: AIResponseInvalid | None = None
        for attempt in range(max_retries + 1):
            retry_system = system
            if attempt > 0:
                retry_system = (
                    system
                    + "\n\n【重要】上一次回复的 JSON 格式有误。"
                    "本次必须输出合法 JSON，不得包含任何 Markdown、注释或多余文字。"
                    "确保所有字符串用双引号、逗号和括号完整闭合。"
                )
                _log.warning(
                    "complete_json_retry attempt=%d endpoint=%s",
                    attempt,
                    endpoint_id,
                )
            text = await self._complete(
                system=retry_system,
                user=user,
                endpoint_id=endpoint_id,
                images=images,
                max_tokens=max_tokens,
                json_mode=True,
                extra_body=extra_body,
            )
            try:
                parse_json_response(text)
                return text
            except AIResponseInvalid as exc:
                last_exc = exc
                if attempt < max_retries:
                    continue
        raise last_exc  # type: ignore[misc]

    async def _complete_json_with_usage(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
        max_retries: int = 2,
        max_tokens: int | None = None,
    ) -> AITextResult:
        """JSON completion implementation with usage metadata."""

        import logging as _logging

        from app.ai.exceptions import AIResponseInvalid
        from app.ai.json_utils import parse_json_response

        _log = _logging.getLogger(__name__)

        last_exc: AIResponseInvalid | None = None
        for attempt in range(max_retries + 1):
            retry_system = system
            if attempt > 0:
                retry_system = (
                    system
                    + "\n\n【重要】上一次回复的 JSON 格式有误。"
                    "本次必须输出合法 JSON，不得包含任何 Markdown、注释或多余文字。"
                    "确保所有字符串用双引号、逗号和括号完整闭合。"
                )
                _log.warning(
                    "complete_json_retry attempt=%d endpoint=%s",
                    attempt,
                    endpoint_id,
                )
            result = await self._stream_collect_with_usage(
                system=retry_system,
                user=user,
                endpoint_id=endpoint_id,
                images=images,
                max_tokens=max_tokens,
                json_mode=True,
            )
            try:
                parse_json_response(result.content)
                return result
            except AIResponseInvalid as exc:
                last_exc = exc
                if attempt < max_retries:
                    continue
        raise last_exc  # type: ignore[misc]

    async def stream(
        self, *, system: str, user: str, endpoint_id: str,
    ) -> AsyncIterator[str]:
        """Streaming completion — yields content chunks to the caller."""

        async def _protected_gen() -> AsyncGenerator[str, None]:
            started_at = time.monotonic()
            try:
                async with self._circuit_breaker.protect():
                    gen = await self._stream(
                        system=system,
                        user=user,
                        endpoint_id=endpoint_id,
                    )
                    async for chunk in gen:
                        yield chunk
            except Exception:
                record_ai_request(
                    self._METRICS_PROVIDER,
                    endpoint_id,
                    "error",
                    time.monotonic() - started_at,
                )
                raise
            record_ai_request(
                self._METRICS_PROVIDER,
                endpoint_id,
                "success",
                time.monotonic() - started_at,
            )

        return _protected_gen()

    async def _stream(
        self, *, system: str, user: str, endpoint_id: str,
    ) -> AsyncIterator[str]:
        """Streaming implementation without circuit breaker wrapping."""

        url = self._chat_url()
        headers = self._headers()
        payload: dict[str, object] = {
            "model": endpoint_id,
            "messages": self._build_messages(system, user),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        stream_timeout = self._STREAM_TIMEOUT

        async def _gen() -> AsyncGenerator[str, None]:
            try:
                async with httpx.AsyncClient(
                    timeout=stream_timeout,
                ) as client:
                    async with client.stream(
                        "POST", url, json=payload, headers=headers,
                    ) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            ArkOpenAIClient._raise_for_status(
                                resp.status_code,
                                body.decode("utf-8", errors="replace"),
                            )
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            chunk = line[6:].strip()
                            if chunk == "[DONE]":
                                break
                            try:
                                chunk_data: dict[str, object] = (
                                    json.loads(chunk)
                                )
                                usage = self._extract_usage(chunk_data)
                                if usage is not None:
                                    self._log_usage(endpoint_id, usage)
                                choices = chunk_data.get("choices")
                                if (
                                    not isinstance(choices, list)
                                    or not choices
                                ):
                                    continue
                                first = choices[0]
                                if not isinstance(first, dict):
                                    continue
                                delta = first.get("delta", {})
                                if not isinstance(delta, dict):
                                    continue
                                content = delta.get("content", "")
                                if not content:
                                    # Fallback: DeepSeek may put
                                    # output in reasoning_content.
                                    content = delta.get(
                                        "reasoning_content", "",
                                    )
                                if content:
                                    yield str(content)
                            except (json.JSONDecodeError, KeyError):
                                continue
            except httpx.TimeoutException as exc:
                raise AIServiceTimeout(
                    "Ark API stream timed out",
                ) from exc
            except httpx.RequestError as exc:
                raise AIServiceUnavailable(
                    f"Network error during Ark stream: {exc}"
                ) from exc

        return _gen()
