"""API request/response schemas for triggers."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --- Requests ---


class CreateWebhookRequest(BaseModel):
    """Create a webhook trigger."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, max_length=200, pattern=r"^[a-z0-9_-]+$")
    input_mapping: dict[str, Any] | None = None


class CreateScheduleRequest(BaseModel):
    """Create a schedule trigger."""

    model_config = ConfigDict(extra="forbid")

    cron_expression: str = Field(..., min_length=1)
    timezone: str = "UTC"
    inputs: dict[str, Any] | None = None


# --- Responses ---


class WebhookTriggerResponse(BaseModel):
    """Webhook trigger response."""

    id: UUID
    workflow_id: UUID
    key: str
    is_active: bool
    input_mapping: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ScheduleTriggerResponse(BaseModel):
    """Schedule trigger response."""

    id: UUID
    workflow_id: UUID
    cron_expression: str
    timezone: str
    is_active: bool
    inputs: dict[str, Any] | None = None
    next_fire_at: datetime | None = None
    last_fired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebhookFireResponse(BaseModel):
    """Response when a webhook is fired."""

    run_id: UUID
    workflow_id: UUID
    status: str
