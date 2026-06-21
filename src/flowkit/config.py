"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Flowkit configuration loaded from environment variables."""

    model_config = {"env_prefix": "FLOWKIT_"}

    # Database
    database_url: str = "postgresql+asyncpg://flowkit:flowkit@localhost:5432/flowkit"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Authentication
    api_key: str = ""

    # Worker
    worker_concurrency: int = 10

    # Scheduler
    scheduler_poll_interval: int = 15  # seconds

    # Logging
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
