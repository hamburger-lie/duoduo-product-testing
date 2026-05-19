"""Redis-based sliding-window rate limiter.

Strategy: fixed-window counter per (user_id, window_key).

Two tiers:
  - "gen"  (generation endpoints) : 20 req / 60 s
  - "std"  (everything else)      : 100 req / 60 s

The limiter is implemented as a FastAPI dependency so it can be applied
per-router or per-endpoint.  The middleware approach was considered but
rejected: we need the authenticated user_id, which is only available
after the auth dependency resolves.

Usage
-----
```python
from app.core.rate_limit import RateLimiter

@router.post("/surveys/generate")
async def generate_survey(
    _: None = Depends(RateLimiter("gen")),
    ...
):
    ...
```

If Redis is unreachable the limiter **fails open** (allows the request)
and logs a warning — availability beats perfect enforcement in MVP.
"""

from __future__ import annotations

import time
from typing import Literal

import redis.asyncio as aioredis
from fastapi import Depends, Request, status

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.models.user import User

logger = get_logger(__name__)

_WINDOW_SECONDS = 60

_LIMITS: dict[str, int] = {
    "gen": 20,   # generation endpoints (survey/evaluation run/report)
    "std": 100,  # all other authenticated endpoints
}

current_user_dependency = Depends(get_current_user)


def _get_redis_client() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(
        settings.redis_url,
        socket_connect_timeout=1,
        socket_timeout=1,
        decode_responses=True,
    )


class RateLimiter:
    """Callable FastAPI dependency that enforces a rate limit.

    Parameters
    ----------
    tier : "gen" | "std"
        Which rate-limit bucket to apply.
    """

    def __init__(self, tier: Literal["gen", "std"] = "std") -> None:
        self.tier = tier
        self.limit = _LIMITS[tier]

    async def __call__(
        self,
        request: Request,
        current_user: User = current_user_dependency,
    ) -> None:
        settings = get_settings()
        if settings.app_env == "testing":
            return

        window = int(time.time()) // _WINDOW_SECONDS
        key = f"rl:{self.tier}:{current_user.id}:{window}"

        try:
            client = _get_redis_client()
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, _WINDOW_SECONDS * 2)  # keep a bit longer for safety
            results = await pipe.execute()
            await client.aclose()
            count: int = results[0]
        except Exception as exc:
            logger.warning("rate_limit_redis_error error=%s tier=%s", exc, self.tier)
            # Fail open — don't block the request when Redis is down
            return

        if count > self.limit:
            retry_after = _WINDOW_SECONDS - (int(time.time()) % _WINDOW_SECONDS)
            raise AppException(
                code="RATE_LIMITED",
                message=f"请求过于频繁，请 {retry_after} 秒后重试",
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"retry_after": retry_after, "limit": self.limit, "tier": self.tier},
            )


class IPRateLimiter:
    """IP-based rate limiter for public (unauthenticated) endpoints.

    Uses the same Redis sliding-window strategy as ``RateLimiter`` but
    keys on the client IP address instead of a user ID.  Designed for
    login / public endpoints where no JWT is available yet.

    Parameters
    ----------
    limit : int
        Max requests per window (default: 10 — conservative for login).
    window : int
        Window size in seconds (default: 60).
    """

    def __init__(self, limit: int = 10, window: int = 60) -> None:
        self.limit = limit
        self.window = window

    async def __call__(self, request: Request) -> None:
        settings = get_settings()
        if settings.app_env == "testing":
            return

        client_ip = (request.client.host if request.client else None) or "unknown"
        window_slot = int(time.time()) // self.window
        key = f"rl:ip:{client_ip}:{window_slot}"

        try:
            client = _get_redis_client()
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window * 2)
            results = await pipe.execute()
            await client.aclose()
            count: int = results[0]
        except Exception as exc:
            logger.warning("ip_rate_limit_redis_error error=%s", exc)
            return  # Fail open

        if count > self.limit:
            retry_after = self.window - (int(time.time()) % self.window)
            raise AppException(
                code="RATE_LIMITED",
                message=f"请求过于频繁，请 {retry_after} 秒后重试",
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"retry_after": retry_after, "limit": self.limit},
            )


# Pre-built dependency instances for convenience
std_rate_limit = RateLimiter("std")
gen_rate_limit = RateLimiter("gen")
login_rate_limit = IPRateLimiter(limit=10, window=60)
