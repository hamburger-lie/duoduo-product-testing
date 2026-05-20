"""Dead Letter Queue (DLQ) using Redis list.

When a Celery task exhausts all retries, the evaluation_id is pushed to
a Redis list ``dlq:evaluations``. The watchdog task scans this list
periodically and logs warnings.

DLQ entries expire after 7 days (TTL on the list key).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DLQ_KEY = "dlq:evaluations"
DLQ_TTL_SECONDS = 7 * 24 * 3600  # 7 days


async def push_to_dlq(
    evaluation_id: int,
    error: str,
    task_id: str | None = None,
) -> None:
    """Push a failed evaluation to the dead letter queue."""
    client: Any | None = None
    try:
        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        entry = json.dumps({
            "evaluation_id": evaluation_id,
            "error": error[:500],
            "task_id": task_id,
            "failed_at": datetime.now(UTC).isoformat(),
        })
        await client.rpush(DLQ_KEY, entry)  # type: ignore[misc]
        await client.expire(DLQ_KEY, DLQ_TTL_SECONDS)
        logger.warning(
            "dlq_push evaluation_id=%s error=%s",
            evaluation_id,
            error[:100],
        )
    except Exception:
        logger.exception("dlq_push_failed evaluation_id=%s", evaluation_id)
    finally:
        if client is not None:
            await client.aclose()


async def pop_from_dlq(count: int = 10) -> list[dict[str, Any]]:
    """Pop up to *count* entries from the DLQ. Returns parsed dicts."""
    client: Any | None = None
    entries: list[dict[str, Any]] = []
    try:
        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        for _ in range(count):
            raw = await client.lpop(DLQ_KEY)  # type: ignore[misc]
            if raw is None:
                break
            entries.append(json.loads(raw))
    except Exception:
        logger.exception("dlq_pop_failed")
    finally:
        if client is not None:
            await client.aclose()
    return entries


async def dlq_length() -> int:
    """Return the current DLQ length."""
    client: Any | None = None
    try:
        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        return int(await client.llen(DLQ_KEY))  # type: ignore[misc]
    except Exception:
        return 0
    finally:
        if client is not None:
            await client.aclose()
