"""Tests for flowkit.engine.graph — Graph runtime."""

import pytest

from flowkit.definition.schema import (
    EdgeDef,
    NodeDef,
    NodeType,
    WorkflowDefinition,
    WorkflowMetadata,
)
from flowkit.engine.graph import Graph


def _linear_workflow() -> WorkflowDefinition:
    """start → http → end"""
    return WorkflowDefinition(
        version="1.0",
        metadata=WorkflowMetadata(name="linear-test"),
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="fetch",
                type=NodeType.http,
                config={
                    "method": "GET",
                    "url": "https://example.com",
                },
            ),
            NodeDef(id="end", type=NodeType.end),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="fetch"),
            EdgeDef(id="e2", source="fetch", target="end"),
        ],
    )


def _branching_workflow() -> WorkflowDefinition:
    """start → if_else → (is_high: approve, else: auto) → end"""
    return WorkflowDefinition(
        version="1.0",
        metadata=WorkflowMetadata(name="branch-test"),
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="check",
                type=NodeType.if_else,
                config={
                    "conditions": [{"id": "is_high", "expression": "true"}],
                },
            ),
            NodeDef(
                id="approve",
                type=NodeType.human_input,
                config={
                    "prompt": "Approve?",
                },
            ),
            NodeDef(
                id="auto",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": "result = {'ok': True}",
                },
            ),
            NodeDef(id="end", type=NodeType.end),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="check"),
            EdgeDef(id="e2", source="check", target="approve", source_handle="is_high"),
            EdgeDef(id="e3", source="check", target="auto", source_handle="else"),
            EdgeDef(id="e4", source="approve", target="end"),
            EdgeDef(id="e5", source="auto", target="end"),
        ],
    )


def _join_workflow() -> WorkflowDefinition:
    """start → (a, b) → end (both a and b must complete)"""
    return WorkflowDefinition(
        version="1.0",
        metadata=WorkflowMetadata(name="join-test"),
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="a",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": "result = {'x': 1}",
                },
            ),
            NodeDef(
                id="b",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": "result = {'y': 2}",
                },
            ),
            NodeDef(id="end", type=NodeType.end),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="a"),
            EdgeDef(id="e2", source="start", target="b"),
            EdgeDef(id="e3", source="a", target="end"),
            EdgeDef(id="e4", source="b", target="end"),
        ],
    )


class TestGraphConstruction:
    def test_nodes_indexed(self):
        g = Graph(_linear_workflow())
        assert g.get_node("start").type == NodeType.start
        assert g.get_node("fetch").type == NodeType.http
        assert g.get_node("end").type == NodeType.end

    def test_unknown_node_raises(self):
        g = Graph(_linear_workflow())
        with pytest.raises(KeyError):
            g.get_node("nonexistent")


class TestStartEndDetection:
    def test_get_start_node(self):
        g = Graph(_linear_workflow())
        assert g.get_start_node().id == "start"

    def test_get_end_node(self):
        g = Graph(_linear_workflow())
        assert g.get_end_node().id == "end"


class TestEdgeQueries:
    def test_outgoing_edges_default(self):
        g = Graph(_linear_workflow())
        edges = g.get_outgoing_edges("start")
        assert len(edges) == 1
        assert edges[0].target == "fetch"

    def test_outgoing_edges_with_handle(self):
        g = Graph(_branching_workflow())
        edges = g.get_outgoing_edges("check", handle="is_high")
        assert len(edges) == 1
        assert edges[0].target == "approve"

    def test_incoming_edges(self):
        g = Graph(_linear_workflow())
        edges = g.get_incoming_edges("end")
        assert len(edges) == 1
        assert edges[0].source == "fetch"

    def test_join_incoming_edges(self):
        g = Graph(_join_workflow())
        edges = g.get_incoming_edges("end")
        assert len(edges) == 2


class TestSuccessorsPredecessors:
    def test_successors_no_filter(self):
        g = Graph(_linear_workflow())
        assert g.get_successors("start") == ["fetch"]

    def test_successors_with_handle(self):
        g = Graph(_branching_workflow())
        assert g.get_successors("check", handle="is_high") == ["approve"]
        assert g.get_successors("check", handle="else") == ["auto"]

    def test_predecessors(self):
        g = Graph(_linear_workflow())
        assert g.get_predecessors("end") == ["fetch"]

    def test_predecessors_join(self):
        g = Graph(_join_workflow())
        preds = g.get_predecessors("end")
        assert sorted(preds) == ["a", "b"]


class TestReadyNodes:
    def test_linear_start_ready(self):
        g = Graph(_linear_workflow())
        ready = g.find_ready_nodes(set())
        assert ready == ["start"]

    def test_linear_after_start(self):
        g = Graph(_linear_workflow())
        ready = g.find_ready_nodes({"start"})
        assert ready == ["fetch"]

    def test_linear_after_all(self):
        g = Graph(_linear_workflow())
        ready = g.find_ready_nodes({"start", "fetch"})
        assert ready == ["end"]

    def test_linear_completed(self):
        g = Graph(_linear_workflow())
        ready = g.find_ready_nodes({"start", "fetch", "end"})
        assert ready == []

    def test_join_needs_both(self):
        g = Graph(_join_workflow())
        ready = g.find_ready_nodes({"start", "a"})
        assert "end" not in ready

    def test_join_both_complete(self):
        g = Graph(_join_workflow())
        ready = g.find_ready_nodes({"start", "a", "b"})
        assert ready == ["end"]


class TestTopologicalOrder:
    def test_linear(self):
        g = Graph(_linear_workflow())
        order = g.topological_order()
        assert order.index("start") < order.index("fetch") < order.index("end")

    def test_branching(self):
        g = Graph(_branching_workflow())
        order = g.topological_order()
        assert order.index("start") < order.index("check")
        assert order.index("check") < order.index("approve")
        assert order.index("check") < order.index("auto")
