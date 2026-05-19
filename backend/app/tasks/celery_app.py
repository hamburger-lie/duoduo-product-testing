from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""

    s = get_settings()
    app = Celery(
        "duoduo",
        broker=s.redis_url,
        backend=s.redis_url,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=4,
        task_soft_time_limit=300,
        task_time_limit=600,
        result_expires=3600,
    )
    app.autodiscover_tasks(["app.tasks"])
    return app


celery_app = create_celery_app()
