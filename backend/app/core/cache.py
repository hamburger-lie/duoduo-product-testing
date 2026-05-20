"""Redis cache utilities with anti-stampede and fail-open semantics.

Features:
- get / set / delete
- TTL jitter (base_ttl +/- 10%) to prevent cache stampede
- Null value caching (short TTL) to prevent cache penetration
- Fail-open: Redis unavailable does not block requests

Usage::

    cache = RedisCache(prefix="product")
    result = await cache.get_or_set(
        key=f"detail:{product_id}",
        factory=lambda: repo.get_by_id(product_id),
        ttl=300,
    )
"""
from __future__ import annotations

import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Sentinel for cached None (distinguishes "not in cache" from "cached as None")
_NULL_SENTINEL = "__NULL__"
_NULL_TTL = 60  # short TTL for null values


def _jitter_ttl(ttl: int) -> int:
    """Add +/- 10% jitter to TTL to prevent cache stampede."""
    delta = max(1, int(ttl * 0.1))
    return ttl + random.randint(-delta, delta)


class RedisCache:
    """Simple Redis cache with prefix namespacing."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    def _full_key(self, key: str) -> str:
        return f"cache:{self._prefix}:{key}"

    def _get_client(self) -> Any:
        settings = get_settings()
        return aioredis.from_url(settings.redis_url, socket_connect_timeout=2)

    async def get(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value). hit=False means cache miss."""
        client: Any | None = None
        try:
            client = self._get_client()
            raw = await client.get(self._full_key(key))
            if raw is None:
                return False, None
            data = json.loads(raw)
            if data == _NULL_SENTINEL:
                return True, None  # cached null
            return True, data
        except Exception:
            logger.debug("cache_get_failed key=%s", key)
            return False, None
        finally:
            if client is not None:
                await client.aclose()

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set a value with jittered TTL. None values use short TTL."""
        client: Any | None = None
        try:
            client = self._get_client()
            if value is None:
                data = json.dumps(_NULL_SENTINEL)
                actual_ttl = _NULL_TTL
            else:
                data = json.dumps(value)
                actual_ttl = _jitter_ttl(ttl)
            await client.set(self._full_key(key), data, ex=actual_ttl)
        except Exception:
            logger.debug("cache_set_failed key=%s", key)
        finally:
            if client is not None:
                await client.aclose()

    async def delete(self, key: str) -> None:
        """Delete a cache entry."""
        client: Any | None = None
        try:
            client = self._get_client()
            await client.delete(self._full_key(key))
        except Exception:
            logger.debug("cache_delete_failed key=%s", key)
        finally:
            if client is not None:
                await client.aclose()

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern (use sparingly)."""
        client: Any | None = None
        try:
            client = self._get_client()
            full_pattern = self._full_key(pattern)
            cursor: int | bytes = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=full_pattern, count=100)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            logger.debug("cache_delete_pattern_failed pattern=%s", pattern)
        finally:
            if client is not None:
                await client.aclose()

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        ttl: int = 300,
    ) -> T:
        """Get from cache or call factory, cache the result, and return it."""
        hit, cached = await self.get(key)
        if hit:
            return cached  # type: ignore[no-any-return]
        result = await factory()
        await self.set(key, result, ttl=ttl)
        return result
