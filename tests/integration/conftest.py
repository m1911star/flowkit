"""Shared fixtures for integration tests — in-memory aiosqlite backend."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from flowkit.definition.loader import compute_checksum, load_dict
from flowkit.engine.graph import Graph
from flowkit.nodes.base import NodeContext
from flowkit.nodes.registry import get_executor
from flowkit.persistence.models import metadata
from flowkit.persistence.repos import (
    NodeRunRepo,
    RunEventRepo,
    WebhookTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool
from flowkit.streaming.emitter import (
    EventEmitter,
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_STARTED,
    NODE_WAITING,
    RUN_COMPLETED,
    RUN_STARTED,
)


# --------------------------------------------------------------------------- #
# Engine / Connection fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite engine for testing."""
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """Yield a connection with auto-rollback for test isolation."""
    async with engine.begin() as connection:
        yield connection


# --------------------------------------------------------------------------- #
# Repository fixtures
# --------------------------------------------------------------------------- #


@dataclass
class Repos:
    """Bundle of all repository instances for convenience."""

    workflow: WorkflowRepo
    version: WorkflowVersionRepo
    run: WorkflowRunRepo
    node_run: NodeRunRepo
    event: RunEventRepo
    webhook: WebhookTriggerRepo


@pytest.fixture
def repos() -> Repos:
    """Provide fresh repo instances (stateless, no setup needed)."""
    return Repos(
        workflow=WorkflowRepo(),
        version=WorkflowVersionRepo(),
        run=WorkflowRunRepo(),
        node_run=NodeRunRepo(),
        event=RunEventRepo(),
        webhook=WebhookTriggerRepo(),
    )


# --------------------------------------------------------------------------- #
# Workflow creation helper
# --------------------------------------------------------------------------- #


async def create_workflow_and_version(
    conn: AsyncConnection,
    repos: Repos,
    definition_dict: dict[str, Any],
    *,
    name: str | None = None,
    publish: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a workflow + version from a definition dict.

    Returns (workflow_row, version_row) dicts.
    """
    wf_name = name or definition_dict.get("metadata", {}).get("name", f"wf-{uuid.uuid4().hex[:8]}")
    wf = await repos.workflow.create(conn, name=wf_name)

    definition = load_dict(definition_dict)
    checksum = compute_checksum(definition)

    ver = await repos.version.create(
        conn,
        workflow_id=wf["id"],
        version=1,
        definition=definition_dict,
        checksum=checksum,
        is_published=publish,
    )
    return wf, ver


# --------------------------------------------------------------------------- #
# Execution helper
# --------------------------------------------------------------------------- #


@dataclass
class ExecutionResult:
    """Result of a full workflow execution."""

    run: dict[str, Any]
    status: str
    pool: VariablePool
    paused_node_id: str | None
    node_runs: list[dict[str, Any]]
    events: list[dict[str, Any]]
    executed_node_ids: list[str] = field(default_factory=list)


def _mark_skipped_subtree(
    graph: Graph,
    non_selected_roots: set[str],
    skipped: set[str],
    completed: set[str],
) -> None:
    """Mark non-selected branch nodes as skipped.

    *non_selected_roots* are the direct successors of a branching node that
    were NOT selected by the handle.  These are unconditionally skipped.

    Their descendants are skipped only when ALL their predecessors are either
    completed, skipped, or in the non-selected set — i.e. no path from the
    selected branch can reach them.  Merge nodes (like ``end``) that also
    receive an edge from the selected branch will NOT be skipped because they
    will have a predecessor that is neither completed nor skipped yet (it's on
    the selected path and hasn't executed).
    """
    queue = list(non_selected_roots)
    for node_id in queue:
        if node_id in completed or node_id in skipped:
            continue
        skipped.add(node_id)
        for child in graph.get_successors(node_id):
            if child in completed or child in skipped:
                continue
            # Only skip a descendant if ALL its predecessors are
            # completed or skipped — meaning no live path reaches it.
            predecessors = graph.get_predecessors(child)
            if all(p in completed or p in skipped for p in predecessors):
                queue.append(child)


async def execute_workflow(
    conn: AsyncConnection,
    definition_dict: dict[str, Any],
    inputs: dict[str, Any],
    repos: Repos,
    workflow_id: uuid.UUID,
    workflow_version_id: uuid.UUID,
) -> ExecutionResult:
    """Execute a workflow to completion (or pause/failure).

    Walks the graph using find_ready_nodes, executing each node with real
    executors.  Handles branching by tracking which successor nodes are
    reachable via handle-selected edges.
    """
    definition = load_dict(definition_dict)
    graph = Graph(definition)
    pool = VariablePool()
    pool.set_workflow_inputs(inputs)

    # Create run in DB
    run = await repos.run.create(
        conn,
        workflow_id=workflow_id,
        workflow_version_id=workflow_version_id,
        inputs=inputs,
    )
    await repos.run.update_status(conn, run["id"], status="running", expected_status="pending")

    event_emitter = EventEmitter(repos.event)
    await event_emitter.emit(conn, run["id"], RUN_STARTED)

    completed: set[str] = set()
    skipped: set[str] = set()
    paused_node_id: str | None = None
    final_status = "completed"
    executed_node_ids: list[str] = []

    while True:
        ready = graph.find_ready_nodes(completed | skipped)
        ready = [n for n in ready if n not in skipped]
        if not ready:
            break

        for node_id in ready:
            node_def = graph.get_node(node_id)
            node_run = await repos.node_run.create(
                conn,
                workflow_run_id=run["id"],
                node_id=node_id,
                node_type=node_def.type.value,
            )
            await repos.node_run.update_status(conn, node_run["id"], status="running")
            await event_emitter.emit(conn, run["id"], NODE_STARTED, node_id=node_id)

            executor = get_executor(node_def.type)
            ctx = NodeContext(
                node_def=node_def,
                variable_pool=pool,
                run_id=run["id"],
                node_run_id=node_run["id"],
            )
            result = await executor.execute(ctx)

            if result.status == NodeState.WAITING:
                await repos.node_run.update_status(conn, node_run["id"], status="waiting")
                await event_emitter.emit(conn, run["id"], NODE_WAITING, node_id=node_id)
                paused_node_id = node_id
                final_status = "paused"
                executed_node_ids.append(node_id)
                break

            if result.status == NodeState.FAILED:
                await repos.node_run.update_status(
                    conn, node_run["id"], status="failed", error=result.error
                )
                await event_emitter.emit(
                    conn, run["id"], NODE_FAILED, node_id=node_id, payload={"error": result.error}
                )
                await repos.run.update_status(conn, run["id"], status="failed")
                final_status = "failed"
                executed_node_ids.append(node_id)
                break

            # Handle branching: skip non-selected successors
            if result.next_handle != "default":
                selected = set(graph.get_successors(node_id, handle=result.next_handle))
                all_succ = set(graph.get_successors(node_id))
                non_selected = all_succ - selected
                _mark_skipped_subtree(graph, non_selected, skipped, completed)

            pool.set_node_outputs(node_id, result.outputs)
            await repos.node_run.update_status(
                conn, node_run["id"], status="completed", outputs=result.outputs
            )
            await event_emitter.emit(conn, run["id"], NODE_COMPLETED, node_id=node_id)
            completed.add(node_id)
            executed_node_ids.append(node_id)
        else:
            continue
        break

    if final_status == "completed":
        await repos.run.update_status(conn, run["id"], status="completed", outputs=pool.to_dict())
        await event_emitter.emit(conn, run["id"], RUN_COMPLETED)
    elif final_status == "paused":
        await repos.run.update_status(
            conn, run["id"], status="paused", variable_pool=pool.to_dict()
        )

    all_node_runs = await repos.node_run.list_by_run(conn, run["id"])
    all_events = await repos.event.list_by_run(conn, run["id"])

    return ExecutionResult(
        run=run,
        status=final_status,
        pool=pool,
        paused_node_id=paused_node_id,
        node_runs=all_node_runs,
        events=all_events,
        executed_node_ids=executed_node_ids,
    )


async def resume_workflow(
    conn: AsyncConnection,
    definition_dict: dict[str, Any],
    execution_result: ExecutionResult,
    repos: Repos,
    human_input_outputs: dict[str, Any],
    paused_node_id: str,
) -> ExecutionResult:
    """Resume a paused workflow from where it stopped.

    Provides human_input_outputs to the paused node, then continues execution.
    """
    definition = load_dict(definition_dict)
    graph = Graph(definition)
    pool = execution_result.pool
    run = execution_result.run

    # Resume run status
    await repos.run.update_status(conn, run["id"], status="running", expected_status="paused")

    event_emitter = EventEmitter(repos.event)

    # Provide outputs for the paused node
    pool.set_node_outputs(paused_node_id, human_input_outputs)

    # Update the waiting node_run to completed
    paused_nr = await repos.node_run.get_by_run_and_node(conn, run["id"], paused_node_id)
    if paused_nr:
        await repos.node_run.update_status(conn, paused_nr["id"], status="running")
        await repos.node_run.update_status(
            conn, paused_nr["id"], status="completed", outputs=human_input_outputs
        )
    await event_emitter.emit(conn, run["id"], NODE_COMPLETED, node_id=paused_node_id)

    # Build completed set from existing completed node_runs
    completed: set[str] = set()
    all_nrs = await repos.node_run.list_by_run(conn, run["id"])
    for nr in all_nrs:
        if nr["status"] == "completed":
            completed.add(nr["node_id"])

    final_status = "completed"
    paused_node: str | None = None
    executed_node_ids: list[str] = list(execution_result.executed_node_ids)

    while True:
        ready = graph.find_ready_nodes(completed)
        if not ready:
            break

        for node_id in ready:
            node_def = graph.get_node(node_id)
            node_run = await repos.node_run.create(
                conn,
                workflow_run_id=run["id"],
                node_id=node_id,
                node_type=node_def.type.value,
            )
            await repos.node_run.update_status(conn, node_run["id"], status="running")
            await event_emitter.emit(conn, run["id"], NODE_STARTED, node_id=node_id)

            executor = get_executor(node_def.type)
            ctx = NodeContext(
                node_def=node_def,
                variable_pool=pool,
                run_id=run["id"],
                node_run_id=node_run["id"],
            )
            result = await executor.execute(ctx)

            if result.status == NodeState.WAITING:
                await repos.node_run.update_status(conn, node_run["id"], status="waiting")
                await event_emitter.emit(conn, run["id"], NODE_WAITING, node_id=node_id)
                paused_node = node_id
                final_status = "paused"
                executed_node_ids.append(node_id)
                break

            if result.status == NodeState.FAILED:
                await repos.node_run.update_status(
                    conn, node_run["id"], status="failed", error=result.error
                )
                await event_emitter.emit(
                    conn, run["id"], NODE_FAILED, node_id=node_id, payload={"error": result.error}
                )
                await repos.run.update_status(conn, run["id"], status="failed")
                final_status = "failed"
                executed_node_ids.append(node_id)
                break

            pool.set_node_outputs(node_id, result.outputs)
            await repos.node_run.update_status(
                conn, node_run["id"], status="completed", outputs=result.outputs
            )
            await event_emitter.emit(conn, run["id"], NODE_COMPLETED, node_id=node_id)
            completed.add(node_id)
            executed_node_ids.append(node_id)
        else:
            continue
        break

    if final_status == "completed":
        await repos.run.update_status(conn, run["id"], status="completed", outputs=pool.to_dict())
        await event_emitter.emit(conn, run["id"], RUN_COMPLETED)
    elif final_status == "paused":
        await repos.run.update_status(
            conn, run["id"], status="paused", variable_pool=pool.to_dict()
        )

    all_node_runs = await repos.node_run.list_by_run(conn, run["id"])
    all_events = await repos.event.list_by_run(conn, run["id"])

    return ExecutionResult(
        run=run,
        status=final_status,
        pool=pool,
        paused_node_id=paused_node,
        node_runs=all_node_runs,
        events=all_events,
        executed_node_ids=executed_node_ids,
    )
