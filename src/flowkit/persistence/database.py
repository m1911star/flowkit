"""Async database engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from flowkit.config import Settings

_engine: AsyncEngine | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        if settings is None:
            from flowkit.config import get_settings

            settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


async def get_connection(
    engine: AsyncEngine | None = None,
) -> AsyncGenerator[AsyncConnection, None]:
    """Yield an async database connection."""
    eng = engine or get_engine()
    async with eng.connect() as conn:
        yield conn


async def dispose_engine() -> None:
    """Dispose the global engine (for shutdown)."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
