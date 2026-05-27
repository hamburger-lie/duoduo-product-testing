from __future__ import annotations

import itertools
import threading
import time

_COUNTER = itertools.count()
_LOCK = threading.Lock()


def generate_snowflake_like_id() -> int:
    """Generate a monotonic bigint-style ID without database extensions."""

    timestamp_ms = int(time.time() * 1000)
    with _LOCK:
        sequence = next(_COUNTER) & 0xFFF
    return (timestamp_ms << 12) | sequence
