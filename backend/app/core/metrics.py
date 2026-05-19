from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram  # type: ignore[import-not-found]

HTTP_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "path_template", "status_code"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path_template"],
    buckets=HTTP_DURATION_BUCKETS,
)
ai_requests_total = Counter(
    "ai_requests_total",
    "Total AI provider requests.",
    ["provider", "endpoint_id", "status"],
)
ai_request_duration_seconds = Histogram(
    "ai_request_duration_seconds",
    "AI provider request duration in seconds.",
    ["provider", "endpoint_id"],
)
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total Celery tasks.",
    ["task_name", "status"],
)
db_pool_size = Gauge(
    "db_pool_size",
    "Current database pool size.",
)
db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "Current checked-out database connections.",
)


def record_http_request(
    method: str,
    path_template: str,
    status_code: int,
    duration: float,
) -> None:
    """Record one HTTP request."""

    http_requests_total.labels(
        method=method,
        path_template=path_template,
        status_code=str(status_code),
    ).inc()
    http_request_duration_seconds.labels(
        method=method,
        path_template=path_template,
    ).observe(duration)


def record_ai_request(
    provider: str,
    endpoint_id: str,
    status: str,
    duration: float,
) -> None:
    """Record one AI provider request."""

    ai_requests_total.labels(
        provider=provider,
        endpoint_id=endpoint_id,
        status=status,
    ).inc()
    ai_request_duration_seconds.labels(
        provider=provider,
        endpoint_id=endpoint_id,
    ).observe(duration)


def record_celery_task(task_name: str, status: str) -> None:
    """Record one Celery task result."""

    celery_tasks_total.labels(task_name=task_name, status=status).inc()


def update_db_pool_metrics(pool_size: int, checked_out: int) -> None:
    """Update database pool gauges."""

    db_pool_size.set(pool_size)
    db_pool_checked_out.set(checked_out)
