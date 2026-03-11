"""Start node executor — passes workflow inputs downstream."""

from __future__ import annotations

from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState


class StartExecutor(NodeExecutor):
    """Entry point of a workflow. Outputs all workflow inputs."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        outputs = dict(ctx.variable_pool._workflow_inputs)
        return NodeResult(status=NodeState.COMPLETED, outputs=outputs)
