"""Arq worker tasks for workflow execution.

This module contains the async task functions that Arq workers execute.
Tasks are enqueued via Redis and processed by worker processes.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from flowkit.definition.loader import load_dict
from flowkit.engine.graph import Graph
from flowkit.nodes.base import NodeContext, NodeResult
from flowkit.nodes.registry import get_executor
from flowkit.persistence.database import get_engine
from flowkit.persistence.repos import (
    NodeRunRepo,
    RunEventRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)
from flowkit.runtime.state import NodeState, RunState
from flowkit.runtime.variable_pool import VariablePool
from flowkit.streaming.emitter import (
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_RESUMED,
    NODE_STARTED,
    NODE_WAITING,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_PAUSED,
    RUN_RESUMED,
    RUN_STARTED,
    EventEmitter,
)

logger = logging.getLogger(__name__)


async def execute_workflow_run(ctx: dict[str, Any], run_id: str) -> None:
    """Execute a workflow run from start to completion or pause.

    This is the main Arq task function for workflow execution.

    Args:
        ctx: Arq context dict (contains redis pool, etc.)
        run_id: Workflow run ID as string (converted to UUID)

    Returns:
        None

    Raises:
        Exception: Any unhandled exception will mark the run as FAILED
    """
    run_uuid = uuid.UUID(run_id)
    engine = get_engine()

    try:
        async with engine.begin() as conn:
            # Load workflow run
            run_repo = WorkflowRunRepo()
            run = await run_repo.get(conn, run_uuid)
            if run is None:
                raise ValueError(f"Workflow run {run_id} not found")

            # Load workflow version
            version_repo = WorkflowVersionRepo()
            version = await version_repo.get(conn, run["workflow_version_id"])
            if version is None:
                raise ValueError(f"Workflow version {run['workflow_version_id']} not found")

            # Parse definition
            definition = load_dict(version["definition"])

            # Build graph
            graph = Graph(definition)

            # Create variable pool and set workflow inputs
            variable_pool = VariablePool()
            if run["inputs"]:
                variable_pool.set_workflow_inputs(run["inputs"])

            # Create event emitter
            event_repo = RunEventRepo()
            emitter = EventEmitter(event_repo, redis_client=None)

            # Update run to RUNNING
            await run_repo.update_status(conn, run_uuid, status=RunState.RUNNING.value)

            # Emit RUN_STARTED
            await emitter.emit(conn, run_uuid, RUN_STARTED)

            # Track completed nodes
            completed_nodes: set[str] = set()

            # Node execution loop
            node_repo = NodeRunRepo()

            while True:
                # Find ready nodes
                ready_node_ids = graph.find_ready_nodes(completed_nodes)

                if not ready_node_ids:
                    # No more ready nodes - workflow is complete
                    break

                # Execute each ready node
                for node_id in ready_node_ids:
                    node_def = graph.get_node(node_id)

                    # Create node run record
                    node_run = await node_repo.create(
                        conn,
                        workflow_run_id=run_uuid,
                        node_id=node_id,
                        node_type=node_def.type.value,
                    )
                    node_run_id = node_run["id"]

                    # Update to RUNNING
                    await node_repo.update_status(conn, node_run_id, status=NodeState.RUNNING.value)

                    # Emit NODE_STARTED
                    await emitter.emit(conn, run_uuid, NODE_STARTED, node_id=node_id)

                    # Get executor
                    executor = get_executor(node_def.type)

                    # Create context
                    node_ctx = NodeContext(
                        node_def=node_def,
                        variable_pool=variable_pool,
                        run_id=run_uuid,
                        node_run_id=node_run_id,
                    )

                    # Execute node
                    result = await executor.execute(node_ctx)

                    # Handle result based on status
                    if result.status == NodeState.WAITING:
                        # Node is waiting for external input
                        await node_repo.update_status(
                            conn, node_run_id, status=NodeState.WAITING.value
                        )
                        await emitter.emit(conn, run_uuid, NODE_WAITING, node_id=node_id)
                        await run_repo.update_status(
                            conn,
                            run_uuid,
                            status=RunState.PAUSED.value,
                            variable_snapshot=variable_pool.to_dict(),
                        )
                        await emitter.emit(conn, run_uuid, RUN_PAUSED)
                        logger.info("Workflow run %s paused at node %s", run_id, node_id)
                        return

                    elif result.status == NodeState.FAILED:
                        # Node failed
                        await node_repo.update_status(
                            conn,
                            node_run_id,
                            status=NodeState.FAILED.value,
                            error=result.error,
                        )
                        await emitter.emit(
                            conn,
                            run_uuid,
                            NODE_FAILED,
                            node_id=node_id,
                            payload={"error": result.error},
                        )
                        await run_repo.update_status(
                            conn, run_uuid, status=RunState.FAILED.value, error=result.error
                        )
                        await emitter.emit(
                            conn, run_uuid, RUN_FAILED, payload={"error": result.error}
                        )
                        logger.error(
                            "Workflow run %s failed at node %s: %s", run_id, node_id, result.error
                        )
                        return

                    elif result.status == NodeState.COMPLETED:
                        # Node completed successfully
                        if result.outputs:
                            variable_pool.set_node_outputs(node_id, result.outputs)

                        await node_repo.update_status(
                            conn,
                            node_run_id,
                            status=NodeState.COMPLETED.value,
                            outputs=result.outputs,
                        )
                        await emitter.emit(
                            conn,
                            run_uuid,
                            NODE_COMPLETED,
                            node_id=node_id,
                            payload={"outputs": result.outputs},
                        )
                        completed_nodes.add(node_id)

            # All nodes completed successfully
            await run_repo.update_status(
                conn,
                run_uuid,
                status=RunState.COMPLETED.value,
                variable_snapshot=variable_pool.to_dict(),
            )
            await emitter.emit(conn, run_uuid, RUN_COMPLETED)
            logger.info("Workflow run %s completed successfully", run_id)

    except Exception as exc:
        # Unhandled exception - mark run as failed
        logger.exception("Workflow run %s encountered unhandled exception", run_id)
        async with engine.begin() as conn:
            run_repo = WorkflowRunRepo()
            await run_repo.update_status(
                conn, run_uuid, status=RunState.FAILED.value, error=str(exc)
            )
            event_repo = RunEventRepo()
            emitter = EventEmitter(event_repo, redis_client=None)
            await emitter.emit(conn, run_uuid, RUN_FAILED, payload={"error": str(exc)})
        raise


async def resume_workflow_run(
    ctx: dict[str, Any], run_id: str, node_id: str, inputs: dict[str, Any] | None = None
) -> None:
    """Resume a paused workflow run from a waiting node.

    Args:
        ctx: Arq context dict
        run_id: Workflow run ID as string
        node_id: The waiting node ID to resume from
        inputs: Optional inputs to provide to the waiting node

    Returns:
        None

    Raises:
        ValueError: If run is not in PAUSED state
        Exception: Any unhandled exception will mark the run as FAILED
    """
    run_uuid = uuid.UUID(run_id)
    engine = get_engine()

    try:
        async with engine.begin() as conn:
            # Load workflow run
            run_repo = WorkflowRunRepo()
            run = await run_repo.get(conn, run_uuid)
            if run is None:
                raise ValueError(f"Workflow run {run_id} not found")

            # Validate run is paused
            if run["status"] != RunState.PAUSED.value:
                raise ValueError(
                    f"Cannot resume run {run_id}: status is {run['status']}, expected {RunState.PAUSED.value}"
                )

            # Load workflow version
            version_repo = WorkflowVersionRepo()
            version = await version_repo.get(conn, run["workflow_version_id"])
            if version is None:
                raise ValueError(f"Workflow version {run['workflow_version_id']} not found")

            # Parse definition
            definition = load_dict(version["definition"])

            # Build graph
            graph = Graph(definition)

            # Restore variable pool
            variable_pool = VariablePool.from_dict(run["variable_snapshot"] or {})

            # If inputs provided, store them for the node
            if inputs:
                variable_pool.set_node_outputs(node_id, inputs)

            # Create event emitter
            event_repo = RunEventRepo()
            emitter = EventEmitter(event_repo, redis_client=None)

            # Update run to RUNNING
            await run_repo.update_status(conn, run_uuid, status=RunState.RUNNING.value)

            # Emit RUN_RESUMED
            await emitter.emit(conn, run_uuid, RUN_RESUMED, node_id=node_id)

            # Update waiting node to COMPLETED
            node_repo = NodeRunRepo()
            waiting_node_run = await node_repo.get_by_run_and_node(conn, run_uuid, node_id)
            if waiting_node_run is None:
                raise ValueError(f"Node run for node {node_id} not found")

            await node_repo.update_status(
                conn,
                waiting_node_run["id"],
                status=NodeState.COMPLETED.value,
                outputs=inputs or {},
            )

            # Emit NODE_RESUMED then NODE_COMPLETED
            await emitter.emit(conn, run_uuid, NODE_RESUMED, node_id=node_id)
            await emitter.emit(
                conn,
                run_uuid,
                NODE_COMPLETED,
                node_id=node_id,
                payload={"outputs": inputs or {}},
            )

            # Build completed set from existing node runs
            completed_nodes: set[str] = set()
            all_node_runs = await node_repo.list_by_run(conn, run_uuid)
            for nr in all_node_runs:
                if nr["status"] == NodeState.COMPLETED.value:
                    completed_nodes.add(nr["node_id"])

            # Continue execution from this point
            while True:
                ready_node_ids = graph.find_ready_nodes(completed_nodes)

                if not ready_node_ids:
                    break

                for ready_node_id in ready_node_ids:
                    node_def = graph.get_node(ready_node_id)

                    # Create node run record
                    node_run = await node_repo.create(
                        conn,
                        workflow_run_id=run_uuid,
                        node_id=ready_node_id,
                        node_type=node_def.type.value,
                    )
                    node_run_id = node_run["id"]

                    # Update to RUNNING
                    await node_repo.update_status(conn, node_run_id, status=NodeState.RUNNING.value)

                    # Emit NODE_STARTED
                    await emitter.emit(conn, run_uuid, NODE_STARTED, node_id=ready_node_id)

                    # Get executor
                    executor = get_executor(node_def.type)

                    # Create context
                    node_ctx = NodeContext(
                        node_def=node_def,
                        variable_pool=variable_pool,
                        run_id=run_uuid,
                        node_run_id=node_run_id,
                    )

                    # Execute node
                    result = await executor.execute(node_ctx)

                    # Handle result
                    if result.status == NodeState.WAITING:
                        await node_repo.update_status(
                            conn, node_run_id, status=NodeState.WAITING.value
                        )
                        await emitter.emit(conn, run_uuid, NODE_WAITING, node_id=ready_node_id)
                        await run_repo.update_status(
                            conn,
                            run_uuid,
                            status=RunState.PAUSED.value,
                            variable_snapshot=variable_pool.to_dict(),
                        )
                        await emitter.emit(conn, run_uuid, RUN_PAUSED)
                        logger.info("Workflow run %s paused at node %s", run_id, ready_node_id)
                        return

                    elif result.status == NodeState.FAILED:
                        await node_repo.update_status(
                            conn,
                            node_run_id,
                            status=NodeState.FAILED.value,
                            error=result.error,
                        )
                        await emitter.emit(
                            conn,
                            run_uuid,
                            NODE_FAILED,
                            node_id=ready_node_id,
                            payload={"error": result.error},
                        )
                        await run_repo.update_status(
                            conn, run_uuid, status=RunState.FAILED.value, error=result.error
                        )
                        await emitter.emit(
                            conn, run_uuid, RUN_FAILED, payload={"error": result.error}
                        )
                        logger.error(
                            "Workflow run %s failed at node %s: %s",
                            run_id,
                            ready_node_id,
                            result.error,
                        )
                        return

                    elif result.status == NodeState.COMPLETED:
                        if result.outputs:
                            variable_pool.set_node_outputs(ready_node_id, result.outputs)

                        await node_repo.update_status(
                            conn,
                            node_run_id,
                            status=NodeState.COMPLETED.value,
                            outputs=result.outputs,
                        )
                        await emitter.emit(
                            conn,
                            run_uuid,
                            NODE_COMPLETED,
                            node_id=ready_node_id,
                            payload={"outputs": result.outputs},
                        )
                        completed_nodes.add(ready_node_id)

            # All nodes completed
            await run_repo.update_status(
                conn,
                run_uuid,
                status=RunState.COMPLETED.value,
                variable_snapshot=variable_pool.to_dict(),
            )
            await emitter.emit(conn, run_uuid, RUN_COMPLETED)
            logger.info("Workflow run %s completed successfully after resume", run_id)

    except Exception as exc:
        logger.exception("Workflow run %s encountered unhandled exception during resume", run_id)
        async with engine.begin() as conn:
            run_repo = WorkflowRunRepo()
            await run_repo.update_status(
                conn, run_uuid, status=RunState.FAILED.value, error=str(exc)
            )
            event_repo = RunEventRepo()
            emitter = EventEmitter(event_repo, redis_client=None)
            await emitter.emit(conn, run_uuid, RUN_FAILED, payload={"error": str(exc)})
        raise
