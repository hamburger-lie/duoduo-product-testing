from __future__ import annotations

import logging
from types import TracebackType

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DistributedLock:
    """Redis distributed lock using SET NX EX atomic operation.

    Usage::

        async with DistributedLock(key=f"eval:{evaluation_id}", ttl=1800) as acquired:
            if not acquired:
                return  # another worker is processing
            ...  # do work

    Fail-open: if Redis is unavailable, the lock is considered acquired
    so that the task can still run (degraded to no-lock mode).
    """

    def __init__(self, key: str, ttl: int = 1800) -> None:
        self.key = f"lock:{key}"
        self.ttl = ttl
        self._acquired = False
        self._client: aioredis.Redis | None = None

    async def __aenter__(self) -> bool:
        settings = get_settings()
        try:
            self._client = aioredis.from_url(
                settings.redis_url, socket_connect_timeout=2
            )
            result = await self._client.set(self.key, "1", nx=True, ex=self.ttl)
            self._acquired = result is not None
        except Exception:
            logger.warning(
                "distributed_lock_acquire_failed",
                extra={"key": self.key},
            )
            self._acquired = True  # fail-open
        return self._acquired

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._acquired and self._client is not None:
            try:
                await self._client.delete(self.key)
            except Exception:
                logger.warning(
                    "distributed_lock_release_failed",
                    extra={"key": self.key},
                )
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
