"""Tests for API key authentication middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from flowkit.api.app import create_app
from flowkit.api.deps import get_db_connection
from flowkit.config import Settings
from flowkit.persistence.models import metadata

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _settings_with_key(api_key: str = "") -> Settings:
    """Create a Settings instance with the given api_key."""
    return Settings(
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        api_key=api_key,
    )


@pytest.fixture
async def app_with_db():
    """Create app with in-memory SQLite DB override."""
    app = create_app()
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async def override_db() -> AsyncGenerator:
        async with engine.begin() as connection:
            yield connection

    app.dependency_overrides[get_db_connection] = override_db
    yield app
    await engine.dispose()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def transport(app):
    return ASGITransport(app=app)


@pytest.fixture
def transport_with_db(app_with_db):
    return ASGITransport(app=app_with_db)


@pytest.mark.asyncio
async def test_no_api_key_configured_allows_all(transport):
    """When settings.api_key is empty, requests pass through."""
    with patch("flowkit.api.middleware.get_settings", return_value=_settings_with_key("")):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_valid_api_key_passes(transport_with_db):
    """X-API-Key header matches configured key → 200."""
    with patch("flowkit.api.middleware.get_settings", return_value=_settings_with_key("secret123")):
        async with AsyncClient(transport=transport_with_db, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/workflows", headers={"X-API-Key": "secret123"}
            )
            # Should pass auth and reach the handler (200 with empty list)
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_api_key_rejects(transport):
    """Wrong key → 401 with error body."""
    with patch("flowkit.api.middleware.get_settings", return_value=_settings_with_key("secret123")):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/workflows", headers={"X-API-Key": "wrong"})
            assert resp.status_code == 401
            body = resp.json()
            assert body["error"]["code"] == "UNAUTHORIZED"
            assert "Invalid or missing API key" in body["error"]["message"]


@pytest.mark.asyncio
async def test_missing_api_key_rejects(transport):
    """No header → 401."""
    with patch("flowkit.api.middleware.get_settings", return_value=_settings_with_key("secret123")):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/workflows")
            assert resp.status_code == 401
            body = resp.json()
            assert body["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_health_endpoint_bypasses_auth(transport):
    """/health always accessible even with api_key configured."""
    with patch("flowkit.api.middleware.get_settings", return_value=_settings_with_key("secret123")):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_docs_endpoint_bypasses_auth(transport):
    """/docs always accessible even with api_key configured."""
    with patch("flowkit.api.middleware.get_settings", return_value=_settings_with_key("secret123")):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/docs")
            # FastAPI returns 200 for /docs (Swagger UI HTML)
            assert resp.status_code == 200
