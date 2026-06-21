"""Node executor registry — maps NodeType to executor classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flowkit.definition.schema import NodeType
from flowkit.nodes.code import CodeExecutor
from flowkit.nodes.end import EndExecutor
from flowkit.nodes.http import HttpExecutor
from flowkit.nodes.human_input import HumanInputExecutor
from flowkit.nodes.if_else import IfElseExecutor
from flowkit.nodes.loop import LoopExecutor
from flowkit.nodes.parallel import ParallelExecutor
from flowkit.nodes.start import StartExecutor
from flowkit.nodes.sub_workflow import SubWorkflowExecutor

if TYPE_CHECKING:
    from flowkit.nodes.base import NodeExecutor

EXECUTOR_REGISTRY: dict[NodeType, type[NodeExecutor]] = {
    NodeType.start: StartExecutor,
    NodeType.end: EndExecutor,
    NodeType.http: HttpExecutor,
    NodeType.code: CodeExecutor,
    NodeType.if_else: IfElseExecutor,
    NodeType.loop: LoopExecutor,
    NodeType.parallel: ParallelExecutor,
    NodeType.human_input: HumanInputExecutor,
    NodeType.sub_workflow: SubWorkflowExecutor,
}


def get_executor(node_type: NodeType) -> NodeExecutor:
    """Return a new instance of the executor for the given node type."""
    cls = EXECUTOR_REGISTRY[node_type]
    return cls()
