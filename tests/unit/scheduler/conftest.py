"""Async test fixtures for scheduler tests using aiosqlite."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from flowkit.persistence.models import metadata

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite engine for testing."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Yield a connection with auto-rollback for test isolation."""
    async with engine.begin() as connection:
        yield connection
