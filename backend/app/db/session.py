from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import load_all_models

settings = get_settings()
load_all_models()
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""

    async with AsyncSessionFactory() as session:
        yield session
