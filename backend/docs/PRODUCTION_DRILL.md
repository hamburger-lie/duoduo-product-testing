# Production Drill

## Purpose

Run this rehearsal before opening the mini program to real users.

## Prerequisites

- Production-like host is reachable by SSH.
- HTTPS domain is configured.
- PostgreSQL, Redis, Qdrant, API, Celery worker, and nginx are configured.
- Current release image has passed Backend CI.
- `.env` contains no development secrets.

## Drill 1: Deploy And Health

1. Deploy the current image.
2. Run `GET /health`.
3. Run `GET /api/v1/health/deep` if enabled for internal operators.
4. Confirm API, Redis, PostgreSQL, Qdrant, and worker status are healthy.

## Drill 2: Migration Forward And Back

1. Run `uv run alembic upgrade head`.
2. Run a login smoke test.
3. Run `uv run alembic downgrade -1`.
4. Run `uv run alembic upgrade head`.
5. Confirm no data loss in existing business tables.

## Drill 3: Backup Restore

1. Create a PostgreSQL backup.
2. Restore the backup into a clean database.
3. Run `uv run alembic upgrade head`.
4. Verify user, product, survey, evaluation, answer, report, conversation, credit, and recharge-order tables.

## Drill 4: Worker Failure

1. Start one evaluation task.
2. Stop the Celery worker.
3. Confirm task state becomes observable and no duplicate credit deduction occurs.
4. Restart the worker.
5. Confirm failed or unfinished work is visible for operator action.

## Drill 5: Rollback

1. Record current image tag and database revision.
2. Deploy the previous image tag.
3. Run the compatible downgrade only when the migration says it is safe.
4. Confirm `GET /health` and login still work.

## Drill 6: Alerts

1. Trigger an application error in staging.
2. Confirm logs contain `request_id` and no secrets.
3. Confirm operator notification channel receives the alert.
