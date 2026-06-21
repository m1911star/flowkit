"""Trigger routes — webhook firing and trigger CRUD."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.api.deps import (
    get_db_connection,
    get_run_repo,
    get_version_repo,
    get_webhook_repo,
    get_workflow_repo,
)
from flowkit.api.schemas.errors import ErrorResponse
from flowkit.api.schemas.triggers import (
    CreateWebhookRequest,
    WebhookFireResponse,
    WebhookTriggerResponse,
)
from flowkit.persistence.repos import (
    WebhookTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)

router = APIRouter(tags=["triggers"])


@router.post(
    "/workflows/{workflow_id}/triggers/webhook",
    response_model=WebhookTriggerResponse,
    status_code=201,
)
async def create_webhook_trigger(
    workflow_id: UUID,
    body: CreateWebhookRequest,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    wf_repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
    hook_repo: Annotated[WebhookTriggerRepo, Depends(get_webhook_repo)],
) -> dict[str, Any]:
    wf = await wf_repo.get(conn, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await hook_repo.create(
        conn,
        workflow_id=workflow_id,
        key=body.key,
        input_mapping=body.input_mapping,
    )


@router.post(
    "/triggers/webhook/{key}",
    response_model=WebhookFireResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def fire_webhook(
    key: str,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    hook_repo: Annotated[WebhookTriggerRepo, Depends(get_webhook_repo)],
    wf_repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
    run_repo: Annotated[WorkflowRunRepo, Depends(get_run_repo)],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trigger = await hook_repo.get_by_key(conn, key)
    if trigger is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    if not trigger["is_active"]:
        raise HTTPException(status_code=409, detail="Webhook is inactive")

    # Get workflow version
    version = await ver_repo.get_published(conn, trigger["workflow_id"])
    if version is None:
        version = await ver_repo.get_latest(conn, trigger["workflow_id"])
    if version is None:
        raise HTTPException(status_code=400, detail="No workflow version available")

    # Apply input mapping
    inputs = payload or {}
    if trigger.get("input_mapping"):
        mapped: dict[str, Any] = {}
        for wf_key, payload_key in trigger["input_mapping"].items():
            if isinstance(payload_key, str) and payload_key in inputs:
                mapped[wf_key] = inputs[payload_key]
        inputs = mapped

    # Create run
    run = await run_repo.create(
        conn,
        workflow_id=trigger["workflow_id"],
        workflow_version_id=version["id"],
        inputs=inputs,
        trigger_type="webhook",
        trigger_id=trigger["id"],
    )
    return {"run_id": run["id"], "workflow_id": trigger["workflow_id"], "status": "pending"}
