"""Lightweight stress-test task for measuring worker concurrency."""
from __future__ import annotations

import time

from app.tasks.celery_app import celery_app


@celery_app.task(name="stress.ping")
def stress_ping(task_index: int, sleep_seconds: float = 2.0) -> dict:
    time.sleep(sleep_seconds)
    return {"index": task_index, "slept": sleep_seconds}
