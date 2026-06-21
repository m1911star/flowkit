"""Dispatcher — tracks node completion and determines next-ready nodes.

The Dispatcher is the state machine that sits between the graph structure
and the executor. It knows which nodes have completed, what handle they
resolved to, and which successors are now eligible to run.

Key responsibilities:
- Track completed, failed, and waiting nodes
- Store node outputs in the variable pool
- Determine successor readiness respecting edge handles (for branching)
- Handle join semantics (nodes with multiple predecessors)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flowkit.runtime.state import NodeState

if TYPE_CHECKING:
    from flowkit.engine.graph import Graph
    from flowkit.nodes.base import NodeResult
    from flowkit.runtime.variable_pool import VariablePool


logger = logging.getLogger(__name__)


class Dispatcher:
    """Tracks node lifecycle and determines which nodes are ready to execute."""

    def __init__(self, graph: Graph, variable_pool: VariablePool) -> None:
        self._graph: Graph = graph
        self._variable_pool: VariablePool = variable_pool
        self._completed_nodes: set[str] = set()
        self._waiting_nodes: set[str] = set()
        self._failed_nodes: set[str] = set()
        self._node_handles: dict[str, str] = {}  # node_id → resolved handle

    # ------------------------------------------------------------------
    # Public read-only properties
    # ------------------------------------------------------------------

    @property
    def completed_nodes(self) -> set[str]:
        return set(self._completed_nodes)

    @property
    def waiting_nodes(self) -> set[str]:
        return set(self._waiting_nodes)

    @property
    def failed_nodes(self) -> set[str]:
        return set(self._failed_nodes)

    # ------------------------------------------------------------------
    # Core dispatch logic
    # ------------------------------------------------------------------

    def on_node_complete(self, node_id: str, result: NodeResult) -> list[str]:
        """Record a node's result and return newly-ready node IDs.

        - COMPLETED nodes are tracked and their outputs stored.
        - FAILED nodes are tracked but do NOT enable successors.
        - WAITING nodes are tracked separately and do NOT enable successors.
        """
        # Store outputs in variable pool regardless of status
        self._variable_pool.set_node_outputs(node_id, result.outputs)

        if result.status == NodeState.WAITING:
            self._waiting_nodes.add(node_id)
            return []

        if result.status == NodeState.FAILED:
            self._completed_nodes.add(node_id)
            self._failed_nodes.add(node_id)
            return []

        # COMPLETED — mark done and record handle
        self._completed_nodes.add(node_id)
        self._node_handles[node_id] = result.next_handle
        logger.debug("Node %s marked complete, handle=%s", node_id, result.next_handle)

        return self._find_newly_ready(node_id)

    def get_ready_nodes(self) -> list[str]:
        """Return all node IDs that are ready to execute right now."""
        ready: list[str] = []
        all_node_ids = [n_id for n_id in self._graph.topological_order()]

        for node_id in all_node_ids:
            if node_id in self._completed_nodes:
                continue
            if node_id in self._waiting_nodes:
                continue
            if self._is_node_ready(node_id):
                ready.append(node_id)

        logger.debug("Ready nodes computed: %s", ready)
        return ready

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_newly_ready(self, completed_node_id: str) -> list[str]:
        """After completing a node, find which of its successors are now ready."""
        handle = self._node_handles.get(completed_node_id, "default")
        successor_ids = self._graph.get_successors(completed_node_id, handle=handle)

        ready: list[str] = []
        for succ_id in successor_ids:
            if succ_id in self._completed_nodes:
                continue
            if self._is_node_ready(succ_id):
                ready.append(succ_id)

        return ready

    def _is_node_ready(self, node_id: str) -> bool:
        """Check if a node's incoming dependencies are satisfied.

        For nodes with no incoming edges (start nodes), always ready.
        """
        incoming_edges = self._graph.get_incoming_edges(node_id)

        if not incoming_edges:
            return True

        # Branching-aware readiness: for incomplete predecessors, check if
        # they are reachable. Unreachable predecessors (on dead branches)
        # are skipped. For completed predecessors, the edge's source_handle
        # must match the handle the source actually resolved to.
        has_satisfied_edge = False
        has_unsatisfied_reachable_predecessor = False

        for edge in incoming_edges:
            source_id = edge.source
            if source_id not in self._completed_nodes:
                if self._is_on_dead_branch(source_id):
                    continue
                has_unsatisfied_reachable_predecessor = True
                continue

            resolved_handle = self._node_handles.get(source_id, "default")
            if edge.source_handle == resolved_handle:
                has_satisfied_edge = True

        if has_unsatisfied_reachable_predecessor:
            return False

        return has_satisfied_edge

    def _is_on_dead_branch(self, node_id: str) -> bool:
        """Check if a node is unreachable because its branch was not taken."""
        incoming_edges = self._graph.get_incoming_edges(node_id)
        if not incoming_edges:
            return False

        for edge in incoming_edges:
            source_id = edge.source
            if source_id not in self._completed_nodes:
                if self._is_on_dead_branch(source_id):
                    continue
                return False

            resolved_handle = self._node_handles.get(source_id, "default")
            if edge.source_handle == resolved_handle:
                return False

        return True
