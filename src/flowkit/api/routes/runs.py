"""Workflow run routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.api.deps import (
    get_db_connection,
    get_event_repo,
    get_node_run_repo,
    get_run_repo,
    get_version_repo,
    get_workflow_repo,
)
from flowkit.api.schemas.runs import (
    NodeRunResponse,
    ResumeRunRequest,
    RunEventResponse,
    RunResponse,
    StartRunRequest,
)
from flowkit.persistence.repos import (
    NodeRunRepo,
    RunEventRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("/workflows/{workflow_id}/run", response_model=RunResponse, status_code=201)
async def start_run(
    workflow_id: UUID,
    body: StartRunRequest,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    wf_repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
    run_repo: Annotated[WorkflowRunRepo, Depends(get_run_repo)],
) -> dict[str, Any]:
    # Verify workflow exists
    wf = await wf_repo.get(conn, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Get published version or latest
    version = await ver_repo.get_published(conn, workflow_id)
    if version is None:
        version = await ver_repo.get_latest(conn, workflow_id)
    if version is None:
        raise HTTPException(status_code=400, detail="No workflow version available")

    # Create run
    run = await run_repo.create(
        conn,
        workflow_id=workflow_id,
        workflow_version_id=version["id"],
        inputs=body.inputs,
        trigger_type="api",
    )
    return run


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    run_repo: Annotated[WorkflowRunRepo, Depends(get_run_repo)],
) -> dict[str, Any]:
    run = await run_repo.get(conn, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/{run_id}/resume", response_model=RunResponse)
async def resume_run(
    run_id: UUID,
    body: ResumeRunRequest,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    run_repo: Annotated[WorkflowRunRepo, Depends(get_run_repo)],
) -> dict[str, Any]:
    run = await run_repo.get(conn, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] not in ("paused", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Run cannot be resumed from status '{run['status']}'",
        )
    # For paused runs, transition to running
    if run["status"] == "paused":
        updated = await run_repo.update_status(
            conn,
            run_id,
            status="running",
            expected_status="paused",
        )
        if not updated:
            raise HTTPException(status_code=409, detail="Concurrent status change")
    # TODO: dispatch resume command to engine
    return await run_repo.get(conn, run_id) or run


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    run_repo: Annotated[WorkflowRunRepo, Depends(get_run_repo)],
) -> dict[str, Any]:
    run = await run_repo.get(conn, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Run is already in terminal state '{run['status']}'",
        )
    updated = await run_repo.update_status(
        conn,
        run_id,
        status="cancelled",
        expected_status=run["status"],
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Concurrent status change")
    return await run_repo.get(conn, run_id) or run


@router.get("/{run_id}/nodes", response_model=list[NodeRunResponse])
async def list_node_runs(
    run_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    node_repo: Annotated[NodeRunRepo, Depends(get_node_run_repo)],
) -> list[dict[str, Any]]:
    return await node_repo.list_by_run(conn, run_id)


@router.get("/{run_id}/events", response_model=list[RunEventResponse])
async def list_run_events(
    run_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    event_repo: Annotated[RunEventRepo, Depends(get_event_repo)],
    after: int | None = None,
) -> list[dict[str, Any]]:
    return await event_repo.list_by_run(conn, run_id, after_sequence=after)
