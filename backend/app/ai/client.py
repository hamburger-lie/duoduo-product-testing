from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol, runtime_checkable

import httpx

from app.ai.exceptions import (
    AIRateLimited,
    AIServiceTimeout,
    AIServiceUnavailable,
)


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
    """OpenAI-compatible client for 火山方舟 (Ark/Doubao)."""

    _TIMEOUT = 60.0

    def __init__(self) -> None:
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
            raise AIRateLimited("Ark API rate limited")
        if status_code >= 500:
            raise AIServiceUnavailable(f"Ark API server error {status_code}")
        if status_code >= 400:
            raise AIServiceUnavailable(
                f"Ark API client error {status_code}: {body[:200]}"
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(self, *, system: str, user: str, endpoint_id: str) -> str:
        payload: dict[str, object] = {
            "model": endpoint_id,
            "messages": self._messages(system, user),
        }
        try:
            async with httpx.AsyncClient(timeout=self._TIMEOUT) as client:
                resp = await client.post(
                    self._chat_url(),
                    json=payload,
                    headers=self._headers(),
                )
        except httpx.TimeoutException as exc:
            raise AIServiceTimeout("Request to Ark API timed out") from exc
        except httpx.RequestError as exc:
            raise AIServiceUnavailable(f"Network error calling Ark API: {exc}") from exc

        if resp.status_code != 200:
            self._raise_for_status(resp.status_code, resp.text)

        data: dict[str, object] = resp.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AIServiceUnavailable("Ark API returned no choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise AIServiceUnavailable("Ark API choice format unexpected")
        message = first.get("message", {})
        if not isinstance(message, dict):
            raise AIServiceUnavailable("Ark API message format unexpected")
        return str(message.get("content", ""))

    async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str:
        """Like complete() but validates the response is parseable JSON."""

        from app.ai.json_utils import parse_json_response

        text = await self.complete(system=system, user=user, endpoint_id=endpoint_id)
        parse_json_response(text)  # raises AIResponseInvalid if unparseable
        return text

    async def stream(
        self, *, system: str, user: str, endpoint_id: str
    ) -> AsyncIterator[str]:
        url = self._chat_url()
        headers = self._headers()
        payload: dict[str, object] = {
            "model": endpoint_id,
            "messages": self._messages(system, user),
            "stream": True,
        }
        timeout = self._TIMEOUT

        async def _gen() -> AsyncGenerator[str, None]:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST", url, json=payload, headers=headers
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
                                    yield str(content)
                            except (json.JSONDecodeError, KeyError):
                                continue
            except httpx.TimeoutException as exc:
                raise AIServiceTimeout("Ark API stream timed out") from exc
            except httpx.RequestError as exc:
                raise AIServiceUnavailable(
                    f"Network error during Ark stream: {exc}"
                ) from exc

        return _gen()
