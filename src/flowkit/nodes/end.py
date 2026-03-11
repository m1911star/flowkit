"""End node executor — resolves output mapping to produce workflow outputs."""

from __future__ import annotations

from typing import Any

from flowkit.definition.schema import EndNodeConfig
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState


class EndExecutor(NodeExecutor):
    """Terminal node. Maps upstream values to workflow outputs."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        config = ctx.node_def.parsed_config()
        outputs: dict[str, Any] = {}

        if isinstance(config, EndNodeConfig) and config.output_mapping:
            for key, ref in config.output_mapping.items():
                outputs[key] = ctx.variable_pool.resolve_value(ref)

        return NodeResult(status=NodeState.COMPLETED, outputs=outputs)
