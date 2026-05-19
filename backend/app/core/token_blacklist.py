from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_redis_client() -> Any:
    """Create a Redis client for token blacklist operations."""

    settings = get_settings()
    return aioredis.from_url(settings.redis_url, socket_connect_timeout=2)


async def blacklist_token(jti: str, expires_at: datetime) -> None:
    """Add a JWT ID to the Redis blacklist until the token expires."""

    ttl = int((expires_at - datetime.now(UTC)).total_seconds())
    if ttl <= 0:
        return

    client: Any | None = None
    try:
        client = _get_redis_client()
        await client.set(f"bl:{jti}", "1", ex=ttl)
    except Exception as exc:
        logger.warning(
            "token_blacklist_set_failed",
            extra={"jti": jti, "error": exc.__class__.__name__},
        )
    finally:
        if client is not None:
            await client.aclose()


async def is_blacklisted(jti: str) -> bool:
    """Return whether a JWT ID is blacklisted, failing open if Redis is down."""

    settings = get_settings()
    if settings.app_env == "testing":
        return False

    client: Any | None = None
    try:
        client = _get_redis_client()
        result = await client.get(f"bl:{jti}")
        return result is not None
    except Exception as exc:
        logger.warning(
            "token_blacklist_check_failed",
            extra={"jti": jti, "error": exc.__class__.__name__},
        )
        return False
    finally:
        if client is not None:
            await client.aclose()
