"""API request/response schemas for workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Requests ---


class CreateWorkflowRequest(BaseModel):
    """Create a new workflow."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class UpdateWorkflowRequest(BaseModel):
    """Update workflow metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None


class CreateVersionRequest(BaseModel):
    """Create a new workflow version with a definition."""

    model_config = ConfigDict(extra="forbid")

    definition: dict[str, Any]
    is_published: bool = False


# --- Responses ---


class WorkflowResponse(BaseModel):
    """Workflow metadata response."""

    id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowVersionResponse(BaseModel):
    """Workflow version response."""

    id: UUID
    workflow_id: UUID
    version: int
    definition: dict[str, Any]
    checksum: str
    is_published: bool
    created_at: datetime


class WorkflowListResponse(BaseModel):
    """Paginated list of workflows."""

    items: list[WorkflowResponse]
    total: int
