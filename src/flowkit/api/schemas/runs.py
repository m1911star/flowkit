"""API request/response schemas for workflow runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# --- Requests ---


class StartRunRequest(BaseModel):
    """Start a workflow run."""

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Any] | None = None


class ResumeRunRequest(BaseModel):
    """Resume a paused/waiting run."""

    model_config = ConfigDict(extra="forbid")

    node_id: str | None = None
    inputs: dict[str, Any] | None = None


# --- Responses ---


class RunResponse(BaseModel):
    """Workflow run response."""

    id: UUID
    workflow_id: UUID
    workflow_version_id: UUID
    status: str
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    error: str | None = None
    trigger_type: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    items: list[RunResponse]
    total: int


class NodeRunResponse(BaseModel):
    """Node execution record."""

    id: UUID
    workflow_run_id: UUID
    node_id: str
    node_type: str
    status: str
    inputs: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class RunEventResponse(BaseModel):
    """Run event record."""

    id: UUID
    workflow_run_id: UUID
    sequence: int
    event_type: str
    node_id: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime
