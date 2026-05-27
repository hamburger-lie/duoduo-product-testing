from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import load_all_models

load_all_models()

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the shared async engine, creating it lazily on first call."""

    global _engine
    if _engine is None:
        from app.core.config import get_settings

        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory, creating it lazily on first call."""

    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


class _LazySessionFactory:
    """Lazy proxy so `AsyncSessionFactory()` still works as a session context manager.

    Celery tasks import this name and call it as ``async with AsyncSessionFactory() as s:``.
    The proxy delegates to the real factory on first access, preserving backward compat
    while keeping engine creation lazy.
    """

    def __call__(self) -> AsyncSession:
        return get_session_factory()()


AsyncSessionFactory = _LazySessionFactory()


async def dispose_engine() -> None:
    """Dispose the engine and reset singletons (called during graceful shutdown)."""

    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session, rolling back on error."""

    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
