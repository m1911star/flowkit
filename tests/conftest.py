"""Shared test fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure test env vars are set to avoid hitting real services."""
    monkeypatch.setenv("FLOWKIT_DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    monkeypatch.setenv("FLOWKIT_REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("FLOWKIT_LOG_LEVEL", "DEBUG")
