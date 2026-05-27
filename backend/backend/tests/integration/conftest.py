"""Integration test fixtures using real PostgreSQL and Redis from docker-compose.

Run with:
    docker compose up -d postgres redis
    uv run pytest tests/integration/ -v

These tests verify real DB operations, transactions, and Redis connectivity.
They are skipped if the services are not reachable.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Real DB URL from docker-compose (host port 5433)
INTEGRATION_DB_URL = os.getenv(
    "INTEGRATION_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/duoduo_test",
)
INTEGRATION_REDIS_URL = os.getenv(
    "INTEGRATION_REDIS_URL",
    "redis://localhost:6380/1",  # DB 1 to avoid conflicts
)


def _check_postgres_reachable() -> bool:
    """Quick sync check if Postgres is up."""
    import asyncio

    async def _check() -> bool:
        try:
            engine = create_async_engine(INTEGRATION_DB_URL)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return True
        except Exception:
            return False

    return asyncio.get_event_loop().run_until_complete(_check())


def _check_redis_reachable() -> bool:
    """Quick sync check if Redis is up."""
    import asyncio

    async def _check() -> bool:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(INTEGRATION_REDIS_URL, socket_connect_timeout=2)
            await client.ping()
            await client.aclose()
            return True
        except Exception:
            return False

    return asyncio.get_event_loop().run_until_complete(_check())


POSTGRES_AVAILABLE = _check_postgres_reachable()
REDIS_AVAILABLE = _check_redis_reachable()

skip_no_postgres = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="PostgreSQL not reachable (docker compose up -d postgres)",
)
skip_no_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason="Redis not reachable (docker compose up -d redis)",
)


@pytest.fixture
async def pg_session() -> AsyncIterator[AsyncSession]:
    """Provide a real PostgreSQL session with automatic rollback."""
    engine = create_async_engine(INTEGRATION_DB_URL)

    # Ensure test database exists with tables
    async with engine.begin() as conn:
        from app.db.models.base import Base

        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session
            # Rollback after each test — no side effects
            await session.rollback()

    await engine.dispose()


@pytest.fixture
async def redis_client() -> AsyncIterator[object]:
    """Provide a real Redis client, flushing test DB after use."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(INTEGRATION_REDIS_URL, socket_connect_timeout=2)
    yield client
    await client.flushdb()
    await client.aclose()
