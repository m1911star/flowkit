"""Human input node executor — pauses execution awaiting external input."""

from __future__ import annotations

from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState


class HumanInputExecutor(NodeExecutor):
    """Return a waiting status so the engine pauses at this node."""

    async def execute(self, ctx: NodeContext) -> NodeResult:
        return NodeResult(
            status=NodeState.WAITING,
            outputs={},
        )
