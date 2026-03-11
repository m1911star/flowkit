"""Async test fixtures for repo tests using aiosqlite."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from flowkit.persistence.models import metadata


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite engine for testing."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    # Create all tables — SQLAlchemy translates JSONB → JSON for SQLite
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Yield a connection with auto-rollback for test isolation."""
    async with engine.begin() as connection:
        yield connection
        # Auto-rollback: the context manager rolls back uncommitted changes
