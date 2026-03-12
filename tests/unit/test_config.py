"""Tests for configuration module."""


from flowkit.config import Settings, get_settings


def test_default_settings() -> None:
    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://test:test@localhost:5432/test"
    assert settings.redis_url == "redis://localhost:6379/1"
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8000
    assert settings.worker_concurrency == 10
    assert settings.scheduler_poll_interval == 15
    assert settings.log_level == "DEBUG"


def test_settings_from_env(monkeypatch: object) -> None:
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setenv("FLOWKIT_API_PORT", "9000")
    mp.setenv("FLOWKIT_WORKER_CONCURRENCY", "20")
    mp.setenv("FLOWKIT_DATABASE_URL", "postgresql+asyncpg://custom:custom@db:5432/custom")
    try:
        settings = Settings()
        assert settings.api_port == 9000
        assert settings.worker_concurrency == 20
        assert settings.database_url == "postgresql+asyncpg://custom:custom@db:5432/custom"
    finally:
        mp.undo()


def test_get_settings_returns_settings() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
