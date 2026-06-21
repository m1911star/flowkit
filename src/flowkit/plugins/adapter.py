"""Plugin adapter — bridges PluginNodeExecutor to internal NodeExecutor."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.plugins.loader import plugin_registry
from flowkit.runtime.state import NodeState

if TYPE_CHECKING:
    from flowkit.plugins.base import PluginResult

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, NodeState] = {
    "completed": NodeState.COMPLETED,
    "failed": NodeState.FAILED,
    "waiting": NodeState.WAITING,
}


class PluginNodeAdapter(NodeExecutor):
    """Adapts a PluginNodeExecutor to the internal NodeExecutor interface."""

    def __init__(self, plugin_node_type: str) -> None:
        self._plugin_node_type = plugin_node_type

    async def execute(self, ctx: NodeContext) -> NodeResult:
        loaded = plugin_registry.get(self._plugin_node_type)
        if loaded is None:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Plugin '{self._plugin_node_type}' not found in registry",
            )

        # Validate config against schema if provided
        config = ctx.node_def.config or {}
        if loaded.config_schema is not None:
            try:
                loaded.config_schema.model_validate(config)
            except Exception as exc:
                return NodeResult(
                    status=NodeState.FAILED,
                    outputs={},
                    error=f"Plugin config validation failed: {exc}",
                )

        # Resolve inputs from variable pool
        inputs: dict[str, Any] = {}
        if config.get("inputs"):
            for name, ref in config["inputs"].items():
                inputs[name] = ctx.variable_pool.resolve_value(ref)

        # Build context dict
        execution_context = {
            "run_id": str(ctx.run_id),
            "node_id": ctx.node_def.id,
            "node_run_id": str(ctx.node_run_id),
        }

        # Execute plugin
        executor = loaded.executor_class()
        try:
            result: PluginResult = await executor.execute(config, inputs, execution_context)
        except Exception as exc:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Plugin execution error: {type(exc).__name__}: {exc}",
            )

        # Map plugin result to NodeResult
        status = _STATUS_MAP.get(result.status, NodeState.FAILED)
        return NodeResult(
            status=status,
            outputs=result.outputs,
            error=result.error,
        )
