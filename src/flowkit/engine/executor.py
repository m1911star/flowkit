"""WorkflowExecutor — orchestrates the full workflow run lifecycle.

Build graph → find ready nodes → execute each → dispatch results → repeat.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flowkit.engine.dispatcher import Dispatcher
from flowkit.engine.graph import Graph
from flowkit.nodes.base import NodeContext
from flowkit.nodes.registry import get_executor
from flowkit.runtime.state import NodeState, RunState
from flowkit.runtime.variable_pool import VariablePool

if TYPE_CHECKING:
    from flowkit.definition.schema import WorkflowDefinition

_MAX_ITERATIONS = 1000

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Structured result of a workflow execution."""

    status: RunState
    run_id: uuid.UUID
    outputs: dict[str, Any]
    events: list[dict[str, Any]]
    waiting_node: str | None = None
    error: str | None = None


class WorkflowExecutor:
    """Run a workflow definition to completion (or pause/failure)."""

    async def execute_workflow(
        self,
        definition: WorkflowDefinition,
        inputs: dict[str, Any],
    ) -> WorkflowResult:
        run_id = uuid.uuid4()
        logger.info("Workflow execution started, run_id=%s", run_id)
        graph = Graph(definition)
        pool = VariablePool(workflow_inputs=inputs)
        dispatcher = Dispatcher(graph, pool)
        events: list[dict[str, Any]] = []

        iterations = 0
        while iterations < _MAX_ITERATIONS:
            iterations += 1
            ready = dispatcher.get_ready_nodes()

            if not ready:
                break

            for node_id in ready:
                node_def = graph.get_node(node_id)
                executor = get_executor(node_def.type)

                ctx = NodeContext(
                    node_def=node_def,
                    variable_pool=pool,
                    run_id=run_id,
                    node_run_id=uuid.uuid4(),
                )

                result = await executor.execute(ctx)
                logger.debug("Node %s executed, status=%s", node_id, result.status.value)
                _ = dispatcher.on_node_complete(node_id, result)

                if result.status == NodeState.COMPLETED:
                    events.append({"type": "node_completed", "node_id": node_id})
                elif result.status == NodeState.WAITING:
                    events.append({"type": "node_waiting", "node_id": node_id})
                    logger.info("Workflow paused, run_id=%s", run_id)
                    return WorkflowResult(
                        status=RunState.PAUSED,
                        run_id=run_id,
                        outputs={},
                        events=events,
                        waiting_node=node_id,
                        error=None,
                    )
                elif result.status == NodeState.FAILED:
                    events.append({"type": "node_failed", "node_id": node_id})
                    logger.info(
                        "Workflow failed, run_id=%s, node=%s", run_id, node_id
                    )
                    return WorkflowResult(
                        status=RunState.FAILED,
                        run_id=run_id,
                        outputs={},
                        events=events,
                        waiting_node=None,
                        error=f"Node '{node_id}' failed: {result.error}",
                    )

        end_node = graph.get_end_node()
        end_outputs = (
            pool.get_node_outputs(end_node.id) if end_node.id in dispatcher.completed_nodes else {}
        )

        logger.info("Workflow completed, run_id=%s", run_id)
        return WorkflowResult(
            status=RunState.COMPLETED,
            run_id=run_id,
            outputs=end_outputs,
            events=events,
            waiting_node=None,
            error=None,
        )
