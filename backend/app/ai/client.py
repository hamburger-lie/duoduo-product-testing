from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol, runtime_checkable

import httpx

from app.ai.exceptions import (
    AIRateLimited,
    AIServiceTimeout,
    AIServiceUnavailable,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class AIClient(Protocol):
    """Protocol for AI completion clients."""

    async def complete(self, *, system: str, user: str, endpoint_id: str) -> str: ...

    async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str: ...

    async def stream(
        self, *, system: str, user: str, endpoint_id: str
    ) -> AsyncIterator[str]: ...


class MockAIClient:
    """Fully functional mock — no external calls."""

    async def complete(self, *, system: str, user: str, endpoint_id: str) -> str:
        return f"Mock response for endpoint {endpoint_id}."

    async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str:
        return f'{{"mock": true, "endpoint_id": "{endpoint_id}"}}'

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
    def _messages(system: str, user: str) -> list[dict[str, str]]:
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

    async def _stream_collect(
        self,
        *,
        system: str,
        user: str,
        endpoint_id: str,
    ) -> str:
        """Stream the response and collect all content into a single string.

        Using streaming avoids client-side read timeouts: each SSE chunk
        resets the httpx read timer even if the model takes minutes to
        finish generating.
        """

        url = self._chat_url()
        headers = self._headers()
        payload: dict[str, object] = {
            "model": endpoint_id,
            "messages": self._messages(system, user),
            "stream": True,
        }

        collected: list[str] = []
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
                    except (json.JSONDecodeError, KeyError):
                        continue

        return "".join(collected)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self, *, system: str, user: str, endpoint_id: str,
    ) -> str:
        """Completion via streaming-collect with retry on timeout and 429."""

        max_attempts = 1 + self._MAX_RETRIES
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return await self._stream_collect(
                    system=system, user=user, endpoint_id=endpoint_id,
                )
            except AIRateLimited as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    wait = 5.0 * (attempt + 1)
                    logger.warning(
                        "ark_rate_limited_retry attempt=%d wait=%.1fs",
                        attempt + 1,
                        wait,
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
        self, *, system: str, user: str, endpoint_id: str,
    ) -> str:
        """Like complete() but validates the response is parseable JSON."""

        from app.ai.json_utils import parse_json_response

        text = await self.complete(
            system=system, user=user, endpoint_id=endpoint_id,
        )
        parse_json_response(text)
        return text

    async def stream(
        self, *, system: str, user: str, endpoint_id: str,
    ) -> AsyncIterator[str]:
        """Streaming completion — yields content chunks to the caller."""

        url = self._chat_url()
        headers = self._headers()
        payload: dict[str, object] = {
            "model": endpoint_id,
            "messages": self._messages(system, user),
            "stream": True,
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
