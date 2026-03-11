"""Dependency injection for FastAPI routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from flowkit.persistence.database import get_engine
from flowkit.persistence.repos import (
    NodeRunRepo,
    RunEventRepo,
    ScheduleTriggerRepo,
    WebhookTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)


async def get_db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Yield a database connection for request scope."""
    engine = get_engine()
    async with engine.begin() as conn:
        yield conn


# Repo singletons — stateless, safe to reuse
_workflow_repo = WorkflowRepo()
_version_repo = WorkflowVersionRepo()
_run_repo = WorkflowRunRepo()
_node_run_repo = NodeRunRepo()
_event_repo = RunEventRepo()
_webhook_repo = WebhookTriggerRepo()
_schedule_repo = ScheduleTriggerRepo()


def get_workflow_repo() -> WorkflowRepo:
    return _workflow_repo


def get_version_repo() -> WorkflowVersionRepo:
    return _version_repo


def get_run_repo() -> WorkflowRunRepo:
    return _run_repo


def get_node_run_repo() -> NodeRunRepo:
    return _node_run_repo


def get_event_repo() -> RunEventRepo:
    return _event_repo


def get_webhook_repo() -> WebhookTriggerRepo:
    return _webhook_repo


def get_schedule_repo() -> ScheduleTriggerRepo:
    return _schedule_repo
