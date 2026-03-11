"""Tests for the Dispatcher — tracks node completion and determines next-ready nodes."""

from __future__ import annotations

import uuid

import pytest

from flowkit.definition.schema import (
    EdgeDef,
    NodeDef,
    NodeType,
    WorkflowDefinition,
    WorkflowMetadata,
)
from flowkit.engine.dispatcher import Dispatcher
from flowkit.engine.graph import Graph
from flowkit.nodes.base import NodeResult
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_definition(
    nodes: list[NodeDef],
    edges: list[EdgeDef],
) -> WorkflowDefinition:
    return WorkflowDefinition(
        version="1.0",
        metadata=WorkflowMetadata(name="test-wf"),
        nodes=nodes,
        edges=edges,
    )


def _ok_result(outputs: dict | None = None, handle: str = "default") -> NodeResult:
    return NodeResult(
        status=NodeState.COMPLETED,
        outputs=outputs or {},
        next_handle=handle,
    )


def _failed_result(error: str = "boom") -> NodeResult:
    return NodeResult(
        status=NodeState.FAILED,
        outputs={},
        error=error,
    )


def _waiting_result() -> NodeResult:
    return NodeResult(
        status=NodeState.WAITING,
        outputs={},
    )


# ---------------------------------------------------------------------------
# Linear workflow:  start -> http -> end
# ---------------------------------------------------------------------------

LINEAR_NODES = [
    NodeDef(id="start", type=NodeType.start),
    NodeDef(id="http1", type=NodeType.http),
    NodeDef(id="end", type=NodeType.end),
]
LINEAR_EDGES = [
    EdgeDef(id="e1", source="start", target="http1"),
    EdgeDef(id="e2", source="http1", target="end"),
]


class TestDispatcherLinear:
    """Linear graph dispatch — no branching."""

    def test_initial_ready_nodes_returns_start(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        ready = dispatcher.get_ready_nodes()
        assert ready == ["start"]

    def test_on_node_complete_returns_successors(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        newly_ready = dispatcher.on_node_complete("start", _ok_result({"trigger": "webhook"}))
        assert newly_ready == ["http1"]

    def test_on_node_complete_stores_outputs_in_pool(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result({"trigger": "webhook"}))
        assert pool.get_node_output("start", "trigger") == "webhook"

    def test_completed_nodes_tracked(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        assert "start" in dispatcher.completed_nodes

    def test_full_linear_dispatch(self) -> None:
        """Walk through the entire linear workflow."""
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        # Start is ready initially
        assert dispatcher.get_ready_nodes() == ["start"]

        # Complete start → http1 becomes ready
        ready = dispatcher.on_node_complete("start", _ok_result({"trigger": "api"}))
        assert ready == ["http1"]

        # Complete http1 → end becomes ready
        ready = dispatcher.on_node_complete("http1", _ok_result({"status_code": 200}))
        assert ready == ["end"]

        # Complete end → no more nodes
        ready = dispatcher.on_node_complete("end", _ok_result({"final": True}))
        assert ready == []

    def test_get_ready_nodes_excludes_completed(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        # start is completed, http1 is now ready, start should not appear
        ready = dispatcher.get_ready_nodes()
        assert "start" not in ready
        assert "http1" in ready


# ---------------------------------------------------------------------------
# Branching workflow:  start -> if_else --(true)-> http1 -> end
#                                        \-(false)-> http2 -> end
# ---------------------------------------------------------------------------

BRANCH_NODES = [
    NodeDef(id="start", type=NodeType.start),
    NodeDef(id="branch", type=NodeType.if_else),
    NodeDef(id="http_true", type=NodeType.http),
    NodeDef(id="http_false", type=NodeType.http),
    NodeDef(id="end", type=NodeType.end),
]
BRANCH_EDGES = [
    EdgeDef(id="e1", source="start", target="branch"),
    EdgeDef(id="e2", source="branch", target="http_true", source_handle="cond_1"),
    EdgeDef(id="e3", source="branch", target="http_false", source_handle="else"),
    EdgeDef(id="e4", source="http_true", target="end"),
    EdgeDef(id="e5", source="http_false", target="end"),
]


class TestDispatcherBranching:
    """Branching dispatch — only the matching handle's successors should become ready."""

    def test_branch_true_enables_correct_successor(self) -> None:
        defn = _make_definition(BRANCH_NODES, BRANCH_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        # Branch resolves to "cond_1" handle → only http_true should be ready
        ready = dispatcher.on_node_complete("branch", _ok_result(handle="cond_1"))
        assert "http_true" in ready
        assert "http_false" not in ready

    def test_branch_false_enables_correct_successor(self) -> None:
        defn = _make_definition(BRANCH_NODES, BRANCH_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        # Branch resolves to "else" handle → only http_false should be ready
        ready = dispatcher.on_node_complete("branch", _ok_result(handle="else"))
        assert "http_false" in ready
        assert "http_true" not in ready

    def test_branch_skipped_nodes_dont_block_end(self) -> None:
        """End node needs at least one predecessor complete, not all (for branching)."""
        defn = _make_definition(BRANCH_NODES, BRANCH_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        dispatcher.on_node_complete("branch", _ok_result(handle="cond_1"))
        # http_false is skipped (not on active path). Complete http_true.
        ready = dispatcher.on_node_complete("http_true", _ok_result())
        # End should be ready even though http_false never completed
        assert "end" in ready

    def test_get_ready_after_branch_respects_handles(self) -> None:
        defn = _make_definition(BRANCH_NODES, BRANCH_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        dispatcher.on_node_complete("branch", _ok_result(handle="else"))

        ready = dispatcher.get_ready_nodes()
        assert "http_false" in ready
        assert "http_true" not in ready


# ---------------------------------------------------------------------------
# Failed and waiting nodes
# ---------------------------------------------------------------------------


class TestDispatcherFailedNodes:
    """Failed nodes should still be tracked but not enable successors."""

    def test_failed_node_tracked_as_completed(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        ready = dispatcher.on_node_complete("http1", _failed_result("timeout"))
        # Failed node should not enable successors
        assert ready == []

    def test_failed_node_in_completed_set(self) -> None:
        defn = _make_definition(LINEAR_NODES, LINEAR_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        dispatcher.on_node_complete("http1", _failed_result())
        assert "http1" in dispatcher.completed_nodes


class TestDispatcherWaitingNodes:
    """Waiting (human_input) nodes should NOT be marked completed."""

    def test_waiting_node_not_marked_completed(self) -> None:
        nodes = [
            NodeDef(id="start", type=NodeType.start),
            NodeDef(id="human", type=NodeType.human_input),
            NodeDef(id="end", type=NodeType.end),
        ]
        edges = [
            EdgeDef(id="e1", source="start", target="human"),
            EdgeDef(id="e2", source="human", target="end"),
        ]
        defn = _make_definition(nodes, edges)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        ready = dispatcher.on_node_complete("human", _waiting_result())

        # Waiting node should not enable successors
        assert ready == []
        # And should not be in completed set
        assert "human" not in dispatcher.completed_nodes

    def test_waiting_node_tracked_in_waiting_set(self) -> None:
        nodes = [
            NodeDef(id="start", type=NodeType.start),
            NodeDef(id="human", type=NodeType.human_input),
            NodeDef(id="end", type=NodeType.end),
        ]
        edges = [
            EdgeDef(id="e1", source="start", target="human"),
            EdgeDef(id="e2", source="human", target="end"),
        ]
        defn = _make_definition(nodes, edges)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        dispatcher.on_node_complete("human", _waiting_result())
        assert "human" in dispatcher.waiting_nodes


# ---------------------------------------------------------------------------
# Parallel join:  start -> a \
#                          b  -> end  (end has two predecessors)
# ---------------------------------------------------------------------------

PARALLEL_NODES = [
    NodeDef(id="start", type=NodeType.start),
    NodeDef(id="a", type=NodeType.http),
    NodeDef(id="b", type=NodeType.http),
    NodeDef(id="end", type=NodeType.end),
]
PARALLEL_EDGES = [
    EdgeDef(id="e1", source="start", target="a"),
    EdgeDef(id="e2", source="start", target="b"),
    EdgeDef(id="e3", source="a", target="end"),
    EdgeDef(id="e4", source="b", target="end"),
]


class TestDispatcherParallelJoin:
    """End node with multiple predecessors — all must complete (non-branching)."""

    def test_join_requires_all_predecessors(self) -> None:
        defn = _make_definition(PARALLEL_NODES, PARALLEL_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        # Complete only a → end should NOT be ready
        ready = dispatcher.on_node_complete("a", _ok_result())
        assert "end" not in ready

    def test_join_ready_after_all_predecessors_complete(self) -> None:
        defn = _make_definition(PARALLEL_NODES, PARALLEL_EDGES)
        graph = Graph(defn)
        pool = VariablePool()
        dispatcher = Dispatcher(graph, pool)

        dispatcher.on_node_complete("start", _ok_result())
        dispatcher.on_node_complete("a", _ok_result())
        ready = dispatcher.on_node_complete("b", _ok_result())
        assert "end" in ready
