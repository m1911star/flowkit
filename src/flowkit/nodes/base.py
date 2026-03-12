"""Node execution abstractions — NodeContext, NodeResult, NodeExecutor ABC.

These form the contract that every node type implements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid

    from flowkit.definition.schema import NodeDef
    from flowkit.runtime.state import NodeState
    from flowkit.runtime.variable_pool import VariablePool


@dataclass
class NodeContext:
    """Execution context passed to every node executor."""

    node_def: NodeDef
    variable_pool: VariablePool
    run_id: uuid.UUID
    node_run_id: uuid.UUID


@dataclass
class NodeResult:
    """Outcome of a single node execution."""

    status: NodeState
    outputs: dict[str, Any]
    error: str | None = None
    next_handle: str = field(default="default")


class NodeExecutor(ABC):
    """Abstract base class for node executors.

    Each node type (start, end, http, code, …) implements this interface.
    """

    @abstractmethod
    async def execute(self, ctx: NodeContext) -> NodeResult:
        """Execute the node and return its result."""
        ...
