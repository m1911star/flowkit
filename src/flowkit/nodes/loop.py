"""Loop node executor — manages iteration over a collection."""

from __future__ import annotations

from flowkit.definition.schema import LoopConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState


class LoopExecutor(NodeExecutor):
    """Evaluate loop items and set up iteration state.

    On first call: resolve items, set index=0, item_variable=first item.
    Returns 'body' handle if items exist, 'completed' if empty.
    Full iteration control is handled by the dispatcher.
    """

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        if not isinstance(config, LoopConfig):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error="Invalid or missing loop node config",
            )

        pool = ctx.variable_pool
        items = pool.resolve_value(config.items)

        if not isinstance(items, list):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Loop items must be a list, got {type(items).__name__}",
            )

        if len(items) > config.max_iterations:
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Loop items ({len(items)}) exceeds max_iterations ({config.max_iterations})",
            )

        if len(items) == 0:
            return NodeResult(
                status=NodeState.COMPLETED,
                outputs={"results": [], "count": 0},
                next_handle="completed",
            )

        pool.set_node_outputs(
            ctx.node_def.id,
            {
                config.item_variable: items[0],
                config.index_variable: 0,
                "_items": items,
                "_total": len(items),
            },
        )

        return NodeResult(
            status=NodeState.COMPLETED,
            outputs={"count": len(items), "results": []},
            next_handle="body",
        )
