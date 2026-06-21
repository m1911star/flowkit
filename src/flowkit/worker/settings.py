"""Arq worker settings configuration.

Defines the WorkerSettings class that Arq uses to configure worker processes.
"""

from __future__ import annotations

import logging

from arq.connections import RedisSettings

from flowkit.config import get_settings
from flowkit.worker.tasks import execute_workflow_run, resume_workflow_run

logger = logging.getLogger(__name__)
settings = get_settings()


async def on_startup(ctx: dict) -> None:  # type: ignore[type-arg]
    """Called when worker starts."""
    logger.info("Worker started")


async def on_shutdown(ctx: dict) -> None:  # type: ignore[type-arg]
    """Called when worker shuts down."""
    logger.info("Worker shutting down")


class WorkerSettings:
    """Arq worker configuration."""

    functions = [execute_workflow_run, resume_workflow_run]

    # Parse Redis URL for Arq
    # Format: redis://host:port/db
    redis_url = settings.redis_url
    redis_parts = redis_url.replace("redis://", "").split("/")
    host_port = redis_parts[0].split(":")
    host = host_port[0] if len(host_port) > 0 else "localhost"
    port = int(host_port[1]) if len(host_port) > 1 else 6379
    database = int(redis_parts[1]) if len(redis_parts) > 1 else 0

    redis_settings = RedisSettings(host=host, port=port, database=database)

    max_jobs = settings.worker_concurrency
    job_timeout = 3600  # 1 hour
    on_startup = on_startup
    on_shutdown = on_shutdown
