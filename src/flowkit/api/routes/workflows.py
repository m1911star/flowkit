"""Workflow CRUD routes."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.api.deps import (
    get_db_connection,
    get_version_repo,
    get_workflow_repo,
)
from flowkit.api.schemas.errors import ErrorResponse
from flowkit.api.schemas.workflows import (
    CreateVersionRequest,
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    VersionDiffResponse,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowVersionResponse,
)
from flowkit.definition.loader import load_dict
from flowkit.persistence.repos import WorkflowRepo, WorkflowVersionRepo

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: CreateWorkflowRequest,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
) -> dict[str, Any]:
    return await repo.create(conn, name=body.name, description=body.description)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    items = await repo.list_all(conn, limit=limit, offset=offset)
    return {"items": items, "total": len(items)}


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_workflow(
    workflow_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
) -> dict[str, Any]:
    wf = await repo.get(conn, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.patch(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    responses={404: {"model": ErrorResponse}},
)
async def update_workflow(
    workflow_id: UUID,
    body: UpdateWorkflowRequest,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
) -> dict[str, Any]:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    updated = await repo.update(conn, workflow_id, **fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf = await repo.get(conn, workflow_id)
    assert wf is not None
    return wf


@router.delete("/{workflow_id}", status_code=204, responses={404: {"model": ErrorResponse}})
async def delete_workflow(
    workflow_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
) -> None:
    deleted = await repo.delete(conn, workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")


# --- Versions ---


@router.post(
    "/{workflow_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_version(
    workflow_id: UUID,
    body: CreateVersionRequest,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    wf_repo: Annotated[WorkflowRepo, Depends(get_workflow_repo)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
) -> dict[str, Any]:
    # Verify workflow exists
    wf = await wf_repo.get(conn, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Validate DSL definition
    try:
        load_dict(body.definition)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid workflow definition: {e}") from e

    # Compute version number
    latest = await ver_repo.get_latest(conn, workflow_id)
    next_version = (latest["version"] + 1) if latest else 1

    # Compute checksum
    canonical = json.dumps(body.definition, sort_keys=True, ensure_ascii=False)
    checksum = hashlib.sha256(canonical.encode()).hexdigest()

    return await ver_repo.create(
        conn,
        workflow_id=workflow_id,
        version=next_version,
        definition=body.definition,
        checksum=checksum,
        is_published=body.is_published,
    )


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_versions(
    workflow_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
) -> list[dict[str, Any]]:
    return await ver_repo.list_by_workflow(conn, workflow_id)


@router.post("/{workflow_id}/versions/{version_id}/publish", response_model=WorkflowVersionResponse)
async def publish_version(
    workflow_id: UUID,
    version_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
) -> dict[str, Any]:
    ver = await ver_repo.get(conn, version_id)
    if ver is None or ver["workflow_id"] != workflow_id:
        raise HTTPException(status_code=404, detail="Version not found")
    # Unpublish any currently published version first
    await ver_repo.unpublish_all(conn, workflow_id)
    await ver_repo.publish(conn, version_id)
    ver["is_published"] = True
    return ver


@router.post(
    "/{workflow_id}/versions/{version_id}/rollback", response_model=WorkflowVersionResponse
)
async def rollback_version(
    workflow_id: UUID,
    version_id: UUID,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
) -> dict[str, Any]:
    """Rollback: unpublish current and publish the specified version."""
    ver = await ver_repo.get(conn, version_id)
    if ver is None or ver["workflow_id"] != workflow_id:
        raise HTTPException(status_code=404, detail="Version not found")
    await ver_repo.unpublish_all(conn, workflow_id)
    await ver_repo.publish(conn, version_id)
    ver["is_published"] = True
    return ver


@router.get("/{workflow_id}/versions/diff", response_model=VersionDiffResponse)
async def diff_versions(
    workflow_id: UUID,
    from_version: int,
    to_version: int,
    conn: Annotated[AsyncConnection, Depends(get_db_connection)],
    ver_repo: Annotated[WorkflowVersionRepo, Depends(get_version_repo)],
) -> dict[str, Any]:
    """Compare two workflow versions and return structural differences."""
    ver_from = await ver_repo.get_by_workflow_and_version(conn, workflow_id, from_version)
    ver_to = await ver_repo.get_by_workflow_and_version(conn, workflow_id, to_version)

    if ver_from is None:
        raise HTTPException(status_code=404, detail=f"Version {from_version} not found")
    if ver_to is None:
        raise HTTPException(status_code=404, detail=f"Version {to_version} not found")

    def_from = ver_from["definition"]
    def_to = ver_to["definition"]

    # Compare nodes
    nodes_from = {n["id"] for n in def_from.get("nodes", [])}
    nodes_to = {n["id"] for n in def_to.get("nodes", [])}

    # Detect modified nodes (same id, different config)
    node_map_from = {n["id"]: n for n in def_from.get("nodes", [])}
    node_map_to = {n["id"]: n for n in def_to.get("nodes", [])}
    common = nodes_from & nodes_to
    modified = [nid for nid in common if node_map_from[nid] != node_map_to[nid]]

    # Compare edges
    edges_from = {(e["source"], e["target"]) for e in def_from.get("edges", [])}
    edges_to = {(e["source"], e["target"]) for e in def_to.get("edges", [])}

    return {
        "workflow_id": workflow_id,
        "from_version": from_version,
        "to_version": to_version,
        "nodes_added": sorted(nodes_to - nodes_from),
        "nodes_removed": sorted(nodes_from - nodes_to),
        "nodes_modified": sorted(modified),
        "edges_added": len(edges_to - edges_from),
        "edges_removed": len(edges_from - edges_to),
    }
