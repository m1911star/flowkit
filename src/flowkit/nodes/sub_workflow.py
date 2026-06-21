"""Sub-workflow node executor — runs a child workflow as a nested execution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from flowkit.definition.loader import load_dict
from flowkit.definition.schema import SubWorkflowConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState, RunState

if TYPE_CHECKING:
    from flowkit.engine.executor import WorkflowResult

logger = logging.getLogger(__name__)


class SubWorkflowExecutor(NodeExecutor):
    """Execute a child workflow definition as a nested workflow."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        if not isinstance(config, SubWorkflowConfig):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error="Invalid or missing sub_workflow node config",
            )

        # Validate the child definition
        try:
            child_def = load_dict(config.definition)
        except Exception as exc:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Invalid child workflow definition: {exc}",
            )

        # Resolve input mapping from parent pool
        pool = ctx.variable_pool
        child_inputs: dict[str, Any] = {}
        for child_key, ref in config.input_mapping.items():
            child_inputs[child_key] = pool.resolve_value(ref)

        # Execute child workflow (late import to avoid circular dependency)
        from flowkit.engine.executor import WorkflowExecutor

        logger.info(
            "Sub-workflow execution started, parent_node=%s", ctx.node_def.id
        )
        executor = WorkflowExecutor()
        child_result: WorkflowResult = await executor.execute_workflow(
            child_def, child_inputs
        )

        # Map child result to parent node result
        if child_result.status == RunState.COMPLETED:
            logger.info(
                "Sub-workflow completed, parent_node=%s", ctx.node_def.id
            )
            return NodeResult(
                status=NodeState.COMPLETED,
                outputs=child_result.outputs,
            )
        elif child_result.status == RunState.PAUSED:
            logger.info(
                "Sub-workflow paused, parent_node=%s", ctx.node_def.id
            )
            return NodeResult(
                status=NodeState.WAITING,
                outputs={},
                error=None,
            )
        else:
            # FAILED
            logger.warning(
                "Sub-workflow failed, parent_node=%s, error=%s",
                ctx.node_def.id,
                child_result.error,
            )
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Sub-workflow failed: {child_result.error}",
            )
