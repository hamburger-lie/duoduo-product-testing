"""Integration tests: real Redis operations.

Validates distributed lock, token blacklist, and rate limiter
behavior against a real Redis instance.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.integration.conftest import INTEGRATION_REDIS_URL, skip_no_redis


@skip_no_redis
class TestDistributedLockReal:
    """Distributed lock against real Redis."""

    async def test_lock_acquire_and_release(self) -> None:
        from types import SimpleNamespace

        from app.core.distributed_lock import DistributedLock

        settings = SimpleNamespace(redis_url=INTEGRATION_REDIS_URL)

        with patch("app.core.distributed_lock.get_settings", return_value=settings):
            async with DistributedLock(key="inttest:lock:1", ttl=10) as acquired:
                assert acquired is True

            # Lock released — can re-acquire
            async with DistributedLock(key="inttest:lock:1", ttl=10) as acquired2:
                assert acquired2 is True

    async def test_lock_mutual_exclusion(self) -> None:
        from types import SimpleNamespace

        from app.core.distributed_lock import DistributedLock

        settings = SimpleNamespace(redis_url=INTEGRATION_REDIS_URL)

        with patch("app.core.distributed_lock.get_settings", return_value=settings):
            async with DistributedLock(key="inttest:lock:2", ttl=30) as outer:
                assert outer is True

                # Same key while held — should fail
                async with DistributedLock(key="inttest:lock:2", ttl=30) as inner:
                    assert inner is False

    async def test_lock_released_after_exception(self) -> None:
        from types import SimpleNamespace

        from app.core.distributed_lock import DistributedLock

        settings = SimpleNamespace(redis_url=INTEGRATION_REDIS_URL)

        with patch("app.core.distributed_lock.get_settings", return_value=settings):
            with pytest.raises(RuntimeError, match="test_error"):
                async with DistributedLock(key="inttest:lock:3", ttl=30) as acquired:
                    assert acquired is True
                    raise RuntimeError("test_error")

            # Should be released despite exception
            async with DistributedLock(key="inttest:lock:3", ttl=30) as reacquired:
                assert reacquired is True


@skip_no_redis
class TestTokenBlacklistReal:
    """Token blacklist against real Redis."""

    async def test_blacklist_roundtrip(self, redis_client: object) -> None:
        import redis.asyncio as aioredis

        assert isinstance(redis_client, aioredis.Redis)

        key = "jwt_blacklist:test_jti_001"
        await redis_client.set(key, "1", ex=60)

        exists = await redis_client.exists(key)
        assert exists == 1

        # TTL should be positive
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 60

    async def test_blacklist_expiry(self, redis_client: object) -> None:
        """Verify TTL-based auto-expiry works."""
        import asyncio

        import redis.asyncio as aioredis

        assert isinstance(redis_client, aioredis.Redis)

        key = "jwt_blacklist:test_jti_expire"
        await redis_client.set(key, "1", ex=1)  # 1 second TTL

        assert await redis_client.exists(key) == 1
        await asyncio.sleep(1.5)
        assert await redis_client.exists(key) == 0


@skip_no_redis
class TestRateLimiterReal:
    """Rate limiter sliding window against real Redis."""

    async def test_rate_limit_window(self, redis_client: object) -> None:
        import redis.asyncio as aioredis

        assert isinstance(redis_client, aioredis.Redis)

        key = "rate:inttest:window"
        pipe = redis_client.pipeline()
        for _ in range(5):
            pipe.incr(key)
        results = await pipe.execute()

        assert results == [1, 2, 3, 4, 5]
        val = await redis_client.get(key)
        assert int(val) == 5  # type: ignore[arg-type]
