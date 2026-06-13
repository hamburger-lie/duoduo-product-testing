from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


class _FakeRedis:
    """Minimal fake Redis for distributed lock tests."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.closed = False

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int = 0
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    async def aclose(self) -> None:
        self.closed = True


def _dev_settings() -> SimpleNamespace:
    return SimpleNamespace(redis_url="redis://test/0")


@pytest.mark.asyncio
async def test_acquire_lock_success() -> None:
    from app.core.distributed_lock import DistributedLock

    fake = _FakeRedis()
    with (
        patch("app.core.distributed_lock.get_settings", return_value=_dev_settings()),
        patch("app.core.distributed_lock.aioredis.from_url", return_value=fake),
    ):
        async with DistributedLock(key="eval:1", ttl=60) as acquired:
            assert acquired is True
            assert "lock:eval:1" in fake.store

    # lock released after exit
    assert "lock:eval:1" not in fake.store


@pytest.mark.asyncio
async def test_lock_already_held() -> None:
    from app.core.distributed_lock import DistributedLock

    fake = _FakeRedis()
    fake.store["lock:eval:2"] = "1"  # pre-held

    with (
        patch("app.core.distributed_lock.get_settings", return_value=_dev_settings()),
        patch("app.core.distributed_lock.aioredis.from_url", return_value=fake),
    ):
        async with DistributedLock(key="eval:2", ttl=60) as acquired:
            assert acquired is False


@pytest.mark.asyncio
async def test_lock_released_after_exit() -> None:
    from app.core.distributed_lock import DistributedLock

    fake = _FakeRedis()
    with (
        patch("app.core.distributed_lock.get_settings", return_value=_dev_settings()),
        patch("app.core.distributed_lock.aioredis.from_url", return_value=fake),
    ):
        async with DistributedLock(key="eval:3", ttl=60) as acquired:
            assert acquired is True

        # re-acquire after release
        async with DistributedLock(key="eval:3", ttl=60) as acquired2:
            assert acquired2 is True


@pytest.mark.asyncio
async def test_redis_unavailable_fail_open() -> None:
    from app.core.distributed_lock import DistributedLock

    with (
        patch("app.core.distributed_lock.get_settings", return_value=_dev_settings()),
        patch(
            "app.core.distributed_lock.aioredis.from_url",
            side_effect=ConnectionError("redis down"),
        ),
    ):
        async with DistributedLock(key="eval:4", ttl=60) as acquired:
            assert acquired is True  # fail-open


@pytest.mark.asyncio
async def test_lock_release_after_exception() -> None:
    from app.core.distributed_lock import DistributedLock

    fake = _FakeRedis()
    with (
        patch("app.core.distributed_lock.get_settings", return_value=_dev_settings()),
        patch("app.core.distributed_lock.aioredis.from_url", return_value=fake),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            async with DistributedLock(key="eval:5", ttl=60) as acquired:
                assert acquired is True
                raise RuntimeError("boom")

        # lock still released despite exception
        assert "lock:eval:5" not in fake.store
