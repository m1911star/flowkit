"""Parallel node executor — fans out over a collection for concurrent processing."""

from __future__ import annotations

from flowkit.definition.schema import ParallelConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState


class ParallelExecutor(NodeExecutor):
    """Evaluate parallel items and set up fan-out state.

    Resolves items from variable pool, stores them as node outputs.
    The dispatcher/executor handles actual parallel execution of
    successor nodes (one per item).

    Outputs:
    - items: the resolved list
    - count: number of items
    - results: empty list (filled by join logic)
    """

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        if not isinstance(config, ParallelConfig):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error="Invalid or missing parallel node config",
            )

        pool = ctx.variable_pool
        items = pool.resolve_value(config.items)

        if not isinstance(items, list):
            return NodeResult(
                status=NodeState.FAILED,
                outputs={},
                error=f"Parallel items must be a list, got {type(items).__name__}",
            )

        if len(items) == 0:
            return NodeResult(
                status=NodeState.COMPLETED,
                outputs={"results": [], "count": 0},
                next_handle="completed",
            )

        # Store items for the executor to fan out
        pool.set_node_outputs(
            ctx.node_def.id,
            {
                "_items": items,
                "_total": len(items),
                config.item_variable: items[0],
                config.index_variable: 0,
                "count": len(items),
                "results": [],
            },
        )

        return NodeResult(
            status=NodeState.COMPLETED,
            outputs={"count": len(items), "results": []},
            next_handle="body",
        )
