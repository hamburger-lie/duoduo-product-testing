"""Tests for Redis cache module."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.cache import RedisCache, _jitter_ttl


def test_jitter_ttl_within_range() -> None:
    """TTL jitter should be within +/- 10%."""
    base = 300
    for _ in range(100):
        result = _jitter_ttl(base)
        assert 270 <= result <= 330


def test_jitter_ttl_minimum_delta() -> None:
    """Even small TTLs get at least 1 second jitter."""
    result = _jitter_ttl(5)
    assert 4 <= result <= 6


class TestRedisCacheUnit:
    """Unit tests with mocked Redis."""

    @pytest.fixture
    def cache(self) -> RedisCache:
        return RedisCache(prefix="test")

    async def test_get_miss(self, cache: RedisCache) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.aclose = AsyncMock()
        with patch.object(cache, "_get_client", return_value=mock_client):
            hit, value = await cache.get("nonexistent")
        assert hit is False
        assert value is None

    async def test_set_and_get(self, cache: RedisCache) -> None:
        store: dict[str, str] = {}

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()

        async def mock_set(key: str, value: str, ex: int | None = None) -> None:
            store[key] = value

        async def mock_get(key: str) -> str | None:
            return store.get(key)

        mock_client.set = mock_set  # type: ignore[assignment]
        mock_client.get = mock_get  # type: ignore[assignment]

        with patch.object(cache, "_get_client", return_value=mock_client):
            await cache.set("item:1", {"name": "test"})
            hit, value = await cache.get("item:1")

        assert hit is True
        assert value == {"name": "test"}

    async def test_get_or_set_cache_hit(self, cache: RedisCache) -> None:
        """Factory should not be called on cache hit."""
        import json

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=json.dumps({"cached": True}))
        mock_client.aclose = AsyncMock()

        factory = AsyncMock(return_value={"fresh": True})

        with patch.object(cache, "_get_client", return_value=mock_client):
            result = await cache.get_or_set("key", factory, ttl=60)

        assert result == {"cached": True}
        factory.assert_not_awaited()

    async def test_get_or_set_cache_miss(self, cache: RedisCache) -> None:
        """Factory should be called on cache miss."""
        store: dict[str, str] = {}

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()

        async def mock_get(key: str) -> str | None:
            return store.get(key)

        async def mock_set(key: str, value: str, ex: int | None = None) -> None:
            store[key] = value

        mock_client.get = mock_get  # type: ignore[assignment]
        mock_client.set = mock_set  # type: ignore[assignment]

        factory = AsyncMock(return_value={"fresh": True})

        with patch.object(cache, "_get_client", return_value=mock_client):
            result = await cache.get_or_set("key", factory, ttl=60)

        assert result == {"fresh": True}
        factory.assert_awaited_once()

    async def test_null_value_cached(self, cache: RedisCache) -> None:
        """None values should be cached with short TTL."""
        store: dict[str, str] = {}

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()

        async def mock_set(key: str, value: str, ex: int | None = None) -> None:
            store[key] = value

        async def mock_get(key: str) -> str | None:
            return store.get(key)

        mock_client.set = mock_set  # type: ignore[assignment]
        mock_client.get = mock_get  # type: ignore[assignment]

        with patch.object(cache, "_get_client", return_value=mock_client):
            await cache.set("empty", None)
            hit, value = await cache.get("empty")

        assert hit is True
        assert value is None

    async def test_redis_failure_returns_miss(self, cache: RedisCache) -> None:
        """Redis failure should fail-open (return miss, not raise)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("down"))
        mock_client.aclose = AsyncMock()

        with patch.object(cache, "_get_client", return_value=mock_client):
            hit, value = await cache.get("key")

        assert hit is False
        assert value is None

    async def test_delete(self, cache: RedisCache) -> None:
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.aclose = AsyncMock()

        with patch.object(cache, "_get_client", return_value=mock_client):
            await cache.delete("item:1")

        mock_client.delete.assert_awaited_once()
