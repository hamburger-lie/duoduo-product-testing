# 2C2G Local Load Test Design

## Goal

Validate how the API behaves under production-like 2 core / 2 GB constraints by running a local Docker Compose profile that limits service resources and uses pre-generated JWT tokens. The goal is stable real-traffic capacity, not maximizing throughput on the local workstation.

## Current Findings

- Token-pool load testing already bypasses login rate limits and can exercise authenticated endpoints directly.
- The current dev API command runs a single Uvicorn worker.
- SQLAlchemy currently uses `DB_POOL_SIZE=10` and `DB_MAX_OVERFLOW=20`, so one process can open up to 30 database connections.
- Production Compose runs 4 API workers but does not explicitly set DB pool sizing. With current defaults, that can attempt up to 120 API database connections before counting worker processes or other clients.
- The 200-user test failed on database-backed endpoints while `/health/live` stayed healthy, which points to connection pool saturation and request queueing rather than CPU-bound application work.

## Recommended Approach

Create a dedicated local load-test Compose override that simulates a 2C2G server by limiting container CPU and memory. Keep it separate from dev and production Compose files so daily development remains unchanged.

The first target profile should be conservative:

- API: 2 Uvicorn workers, about 1.0 to 1.3 CPU, 768 MB to 1 GB memory.
- Postgres: about 0.5 to 0.7 CPU, 512 MB to 768 MB memory.
- Redis: small fixed budget, about 0.1 CPU and 128 MB memory.
- Celery worker: disabled for pure read tests, or limited to the remaining small budget for full-flow tests.

## Database Pool Design

Add explicit DB pool controls:

- `DB_POOL_SIZE`: initial recommendation 6 to 8 per API worker.
- `DB_MAX_OVERFLOW`: initial recommendation 4 to 8 per API worker.
- `DB_POOL_TIMEOUT`: new setting, initial recommendation 2 seconds.

For a 2-worker API with `DB_POOL_SIZE=8` and `DB_MAX_OVERFLOW=4`, the API can open up to 24 database connections. This leaves room under Postgres defaults for admin sessions, Celery, migrations, and operational tools.

Fast pool timeout is intentional. Waiting 30 seconds for a database connection makes users experience a frozen system and turns overload into long tail latency. A 2-second timeout exposes overload quickly and makes capacity limits easier to observe.

## Compose Changes

Add a local-only file named `docker-compose.loadtest-2c2g.yml`.

This file should:

- Override the API command to run 2 Uvicorn workers.
- Set explicit `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, and `DB_POOL_TIMEOUT`.
- Apply CPU and memory limits to API, Postgres, Redis, and optionally Celery.
- Keep the existing service names and network so the current Locust token flow continues to work.

Production Compose should also receive explicit DB pool environment variables, but production resource limits should stay conservative for 2C2G unless the server is upgraded.

## Load-Test Method

Use the existing token-pool Locust file and run capacity steps instead of jumping directly to 200 users:

1. 20 users for 2 to 3 minutes.
2. 50 users for 2 to 3 minutes.
3. 80 users for 2 to 3 minutes.
4. 100 users for 2 to 3 minutes.
5. 150 users only if the previous stage is stable.
6. 200 users only as a stress ceiling test, not as an expected 2C2G target.

Each stage should record request count, failure rate, P50/P95/P99 latency, API memory, API CPU, Postgres CPU, Postgres connections, and DB pool checked-out metrics.

## Success Criteria

A stage is considered stable when:

- Failure rate is below 1%.
- P95 latency is below 1 second for ordinary read endpoints, or below 2 seconds for mixed read/write flow.
- DB pool checked-out count does not remain pinned at the pool ceiling.
- API memory does not grow continuously during the stage.
- Postgres remains responsive and does not show connection exhaustion.

If a higher stage fails because the pool is saturated but CPU and memory still have headroom, tune pool sizes cautiously. If CPU or memory are saturated, the stage exceeds the realistic 2C2G capacity.

## Later Optimizations

After baseline capacity is known, add Redis caching for the hot `GET /api/v1/personas` path. This endpoint is read-heavy in the current Locust profile and mostly returns reusable system persona data. Cache invalidation should happen on private persona create, update, and delete.

PgBouncer should be considered only after the app-level pool and worker counts are explicit and measured. It is useful for connection multiplexing, but it should not hide slow queries or oversized worker counts.

## Out of Scope

- Upgrading server hardware.
- Changing business behavior of API endpoints.
- Replacing the existing token-pool load-test strategy.
- Building a full production observability stack beyond the metrics already exposed by the app.
