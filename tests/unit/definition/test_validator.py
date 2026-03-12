"""Tests for flowkit.definition.validator — all 32 validation rules."""

from __future__ import annotations

from flowkit.definition.schema import (
    DataType,
    EdgeDef,
    InputDef,
    NodeDef,
    NodeType,
    OutputDef,
    WorkflowDefinition,
    WorkflowMetadata,
)
from flowkit.definition.validator import ValidationError, validate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta() -> WorkflowMetadata:
    return WorkflowMetadata(name="test-wf")


def _wf(
    nodes: list[NodeDef] | None = None,
    edges: list[EdgeDef] | None = None,
    version: str = "1.0",
    inputs: dict | None = None,
    outputs: dict | None = None,
) -> WorkflowDefinition:
    """Build a WorkflowDefinition, bypassing Pydantic's version validator for tests."""
    if nodes is None:
        nodes = [
            NodeDef(id="start", type=NodeType.start),
            NodeDef(id="end", type=NodeType.end),
        ]
    if edges is None:
        edges = [EdgeDef(id="e1", source="start", target="end")]

    # Use model_construct to bypass version validation so we can test V-001
    return WorkflowDefinition.model_construct(
        version=version,
        metadata=_meta(),
        inputs={k: InputDef(**v) if isinstance(v, dict) else v for k, v in (inputs or {}).items()},
        outputs={
            k: OutputDef(**v) if isinstance(v, dict) else v for k, v in (outputs or {}).items()
        },
        nodes=nodes,
        edges=edges,
    )


def _valid_wf() -> WorkflowDefinition:
    """Return a minimal valid workflow (start→end)."""
    return _wf()


def _codes(errors: list[ValidationError]) -> set[str]:
    return {e.code for e in errors}


def _errors_with_code(errors: list[ValidationError], code: str) -> list[ValidationError]:
    return [e for e in errors if e.code == code]


# ===========================================================================
# V-001: version must be "1.0"
# ===========================================================================


class TestV001VersionMustBe10:
    def test_valid_version(self):
        errors = validate(_valid_wf())
        assert "V-001" not in _codes(errors)

    def test_invalid_version(self):
        wf = _wf(version="2.0")
        errors = validate(wf)
        assert "V-001" in _codes(errors)

    def test_empty_version(self):
        wf = _wf(version="")
        errors = validate(wf)
        assert "V-001" in _codes(errors)


# ===========================================================================
# V-002: at least 2 nodes
# ===========================================================================


class TestV002AtLeast2Nodes:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-002" not in _codes(errors)

    def test_single_node(self):
        wf = _wf(
            nodes=[NodeDef(id="start", type=NodeType.start)],
            edges=[],
        )
        errors = validate(wf)
        assert "V-002" in _codes(errors)

    def test_zero_nodes(self):
        wf = _wf(nodes=[], edges=[])
        errors = validate(wf)
        assert "V-002" in _codes(errors)


# ===========================================================================
# V-003: all node IDs unique
# ===========================================================================


class TestV003UniqueNodeIds:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-003" not in _codes(errors)

    def test_duplicate_node_ids(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(id="start", type=NodeType.start),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[EdgeDef(id="e1", source="start", target="end")],
        )
        errors = validate(wf)
        assert "V-003" in _codes(errors)


# ===========================================================================
# V-004: all edge IDs unique
# ===========================================================================


class TestV004UniqueEdgeIds:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-004" not in _codes(errors)

    def test_duplicate_edge_ids(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="mid",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="mid"),
                EdgeDef(id="e1", source="mid", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-004" in _codes(errors)


# ===========================================================================
# V-005: edge source/target reference existing nodes
# ===========================================================================


class TestV005EdgeRefsExist:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-005" not in _codes(errors)

    def test_unknown_source(self):
        wf = _wf(
            edges=[EdgeDef(id="e1", source="nonexistent", target="end")],
        )
        errors = validate(wf)
        assert "V-005" in _codes(errors)

    def test_unknown_target(self):
        wf = _wf(
            edges=[EdgeDef(id="e1", source="start", target="nonexistent")],
        )
        errors = validate(wf)
        assert "V-005" in _codes(errors)


# ===========================================================================
# V-006: no self-loops
# ===========================================================================


class TestV006NoSelfLoops:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-006" not in _codes(errors)

    def test_self_loop(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="mid",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="mid"),
                EdgeDef(id="e2", source="mid", target="mid"),
                EdgeDef(id="e3", source="mid", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-006" in _codes(errors)


# ===========================================================================
# V-007: exactly one start node
# ===========================================================================


class TestV007ExactlyOneStart:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-007" not in _codes(errors)

    def test_no_start(self):
        wf = _wf(
            nodes=[
                NodeDef(id="end", type=NodeType.end),
                NodeDef(
                    id="other",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
            ],
            edges=[EdgeDef(id="e1", source="other", target="end")],
        )
        errors = validate(wf)
        assert "V-007" in _codes(errors)

    def test_multiple_starts(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start1", type=NodeType.start),
                NodeDef(id="start2", type=NodeType.start),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start1", target="end"),
                EdgeDef(id="e2", source="start2", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-007" in _codes(errors)


# ===========================================================================
# V-008: exactly one end node
# ===========================================================================


class TestV008ExactlyOneEnd:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-008" not in _codes(errors)

    def test_no_end(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="other",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
            ],
            edges=[EdgeDef(id="e1", source="start", target="other")],
        )
        errors = validate(wf)
        assert "V-008" in _codes(errors)

    def test_multiple_ends(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(id="end1", type=NodeType.end),
                NodeDef(id="end2", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="end1"),
            ],
        )
        errors = validate(wf)
        assert "V-008" in _codes(errors)


# ===========================================================================
# V-009: start node has 0 incoming edges
# ===========================================================================


class TestV009StartNoIncoming:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-009" not in _codes(errors)

    def test_start_has_incoming(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="mid",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="mid"),
                EdgeDef(id="e2", source="mid", target="start"),
                EdgeDef(id="e3", source="mid", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-009" in _codes(errors)


# ===========================================================================
# V-010: start node has exactly 1 outgoing edge
# ===========================================================================


class TestV010StartOneOutgoing:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-010" not in _codes(errors)

    def test_start_zero_outgoing(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[],
        )
        errors = validate(wf)
        assert "V-010" in _codes(errors)

    def test_start_two_outgoing(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="mid",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="mid"),
                EdgeDef(id="e2", source="start", target="end"),
                EdgeDef(id="e3", source="mid", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-010" in _codes(errors)


# ===========================================================================
# V-011: end node has 0 outgoing edges
# ===========================================================================


class TestV011EndNoOutgoing:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-011" not in _codes(errors)

    def test_end_has_outgoing(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="mid",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="mid"),
                EdgeDef(id="e2", source="mid", target="end"),
                EdgeDef(id="e3", source="end", target="mid"),
            ],
        )
        errors = validate(wf)
        assert "V-011" in _codes(errors)


# ===========================================================================
# V-012: end node has ≥1 incoming edges
# ===========================================================================


class TestV012EndHasIncoming:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-012" not in _codes(errors)

    def test_end_no_incoming(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="mid",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="mid"),
            ],
        )
        errors = validate(wf)
        assert "V-012" in _codes(errors)


# ===========================================================================
# V-013: graph is a DAG (no cycles)
# ===========================================================================


class TestV013DAGNoCycles:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-013" not in _codes(errors)

    def test_cycle(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="a",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(
                    id="b",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="a"),
                EdgeDef(id="e2", source="a", target="b"),
                EdgeDef(id="e3", source="b", target="a"),
                EdgeDef(id="e4", source="b", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-013" in _codes(errors)


# ===========================================================================
# V-014: all nodes reachable from start
# ===========================================================================


class TestV014AllReachable:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-014" not in _codes(errors)

    def test_unreachable_node(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="orphan",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-014" in _codes(errors)
        orphan_errors = _errors_with_code(errors, "V-014")
        assert any("orphan" in e.message for e in orphan_errors)


# ===========================================================================
# V-015: end node reachable from every non-end node
# ===========================================================================


class TestV015EndReachable:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-015" not in _codes(errors)

    def test_dead_end_node(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="a",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(
                    id="b",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="a"),
                EdgeDef(id="e2", source="a", target="end"),
                # b is connected from start but has no path to end
                EdgeDef(id="e3", source="a", target="b"),
            ],
        )
        errors = validate(wf)
        assert "V-015" in _codes(errors)
        assert any("'b'" in e.message for e in _errors_with_code(errors, "V-015"))


# ===========================================================================
# V-016: node ID matches pattern [a-z0-9_]+
# ===========================================================================


class TestV016NodeIdPattern:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-016" not in _codes(errors)

    def test_invalid_node_id_caught_by_pydantic(self):
        """Pydantic already validates this, but the validator also checks it."""
        # We use model_construct to bypass Pydantic validation
        node = NodeDef.model_construct(
            id="Invalid-ID", type=NodeType.code, label=None, config=None, position=None
        )
        wf = WorkflowDefinition.model_construct(
            version="1.0",
            metadata=_meta(),
            inputs={},
            outputs={},
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                node,
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="Invalid-ID"),
                EdgeDef(id="e2", source="Invalid-ID", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-016" in _codes(errors)


# ===========================================================================
# V-017: if_else condition has matching edge
# ===========================================================================


class TestV017IfElseConditionEdge:
    def test_valid_if_else(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="check",
                    type=NodeType.if_else,
                    config={
                        "conditions": [{"id": "is_high", "expression": "x == 'high'"}],
                    },
                ),
                NodeDef(
                    id="high_path",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(
                    id="low_path",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="check"),
                EdgeDef(id="e2", source="check", target="high_path", source_handle="is_high"),
                EdgeDef(id="e3", source="check", target="low_path", source_handle="else"),
                EdgeDef(id="e4", source="high_path", target="end"),
                EdgeDef(id="e5", source="low_path", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-017" not in _codes(errors)

    def test_missing_condition_edge(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="check",
                    type=NodeType.if_else,
                    config={
                        "conditions": [{"id": "is_high", "expression": "x == 'high'"}],
                    },
                ),
                NodeDef(
                    id="low_path",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="check"),
                # No is_high edge!
                EdgeDef(id="e3", source="check", target="low_path", source_handle="else"),
                EdgeDef(id="e5", source="low_path", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-017" in _codes(errors)


# ===========================================================================
# V-018: if_else must have 'else' handle edge
# ===========================================================================


class TestV018IfElseElseEdge:
    def test_has_else(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="check",
                    type=NodeType.if_else,
                    config={
                        "conditions": [{"id": "c1", "expression": "x > 0"}],
                    },
                ),
                NodeDef(
                    id="a",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(
                    id="b",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="check"),
                EdgeDef(id="e2", source="check", target="a", source_handle="c1"),
                EdgeDef(id="e3", source="check", target="b", source_handle="else"),
                EdgeDef(id="e4", source="a", target="end"),
                EdgeDef(id="e5", source="b", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-018" not in _codes(errors)

    def test_missing_else(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="check",
                    type=NodeType.if_else,
                    config={
                        "conditions": [{"id": "c1", "expression": "x > 0"}],
                    },
                ),
                NodeDef(
                    id="a",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="check"),
                EdgeDef(id="e2", source="check", target="a", source_handle="c1"),
                EdgeDef(id="e4", source="a", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-018" in _codes(errors)


# ===========================================================================
# V-019: loop must have 'body' and 'completed' handle edges
# ===========================================================================


class TestV019LoopHandles:
    def test_valid_loop(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="loop_node",
                    type=NodeType.loop,
                    config={
                        "items": "{{nodes.start.output.list}}",
                    },
                ),
                NodeDef(
                    id="body_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="loop_node"),
                EdgeDef(id="e2", source="loop_node", target="body_node", source_handle="body"),
                EdgeDef(id="e3", source="loop_node", target="end", source_handle="completed"),
                EdgeDef(id="e4", source="body_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-019" not in _codes(errors)

    def test_missing_body(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="loop_node",
                    type=NodeType.loop,
                    config={
                        "items": "{{nodes.start.output.list}}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="loop_node"),
                EdgeDef(id="e2", source="loop_node", target="end", source_handle="completed"),
            ],
        )
        errors = validate(wf)
        v019 = _errors_with_code(errors, "V-019")
        assert any("body" in e.message for e in v019)

    def test_missing_completed(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="loop_node",
                    type=NodeType.loop,
                    config={
                        "items": "{{nodes.start.output.list}}",
                    },
                ),
                NodeDef(
                    id="body_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="loop_node"),
                EdgeDef(id="e2", source="loop_node", target="body_node", source_handle="body"),
                EdgeDef(id="e3", source="body_node", target="end"),
            ],
        )
        errors = validate(wf)
        v019 = _errors_with_code(errors, "V-019")
        assert any("completed" in e.message for e in v019)


# ===========================================================================
# V-020: http url must be non-empty
# ===========================================================================


class TestV020HttpUrl:
    def test_valid(self):
        wf = _wf(
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
        errors = validate(wf)
        assert "V-020" not in _codes(errors)

    def test_empty_url(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "GET",
                        "url": "",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-020" in _codes(errors)

    def test_whitespace_url(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "GET",
                        "url": "   ",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-020" in _codes(errors)


# ===========================================================================
# V-021: code source must be non-empty
# ===========================================================================


class TestV021CodeSource:
    def test_valid(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="code_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="code_node"),
                EdgeDef(id="e2", source="code_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-021" not in _codes(errors)

    def test_empty_source(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="code_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="code_node"),
                EdgeDef(id="e2", source="code_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-021" in _codes(errors)


# ===========================================================================
# V-022: code language must be 'python'
# ===========================================================================


class TestV022CodeLanguage:
    def test_valid_python(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="code_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="code_node"),
                EdgeDef(id="e2", source="code_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-022" not in _codes(errors)

    def test_invalid_language(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="code_node",
                    type=NodeType.code,
                    config={
                        "language": "javascript",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="code_node"),
                EdgeDef(id="e2", source="code_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-022" in _codes(errors)


# ===========================================================================
# V-023: human_input prompt non-empty
# ===========================================================================


class TestV023HumanInputPrompt:
    def test_valid(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="input_node",
                    type=NodeType.human_input,
                    config={
                        "prompt": "Please approve",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="input_node"),
                EdgeDef(id="e2", source="input_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-023" not in _codes(errors)

    def test_empty_prompt(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="input_node",
                    type=NodeType.human_input,
                    config={
                        "prompt": "",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="input_node"),
                EdgeDef(id="e2", source="input_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-023" in _codes(errors)


# ===========================================================================
# V-024: input type mismatch (default vs declared type)
# ===========================================================================


class TestV024InputTypeMismatch:
    def test_valid_default(self):
        wf = _wf(
            inputs={"name": InputDef(type=DataType.string, default="hello")},
        )
        errors = validate(wf)
        assert "V-024" not in _codes(errors)

    def test_mismatched_default(self):
        wf = _wf(
            inputs={"name": InputDef(type=DataType.string, default=42)},
        )
        errors = validate(wf)
        assert "V-024" in _codes(errors)

    def test_bool_not_number(self):
        wf = _wf(
            inputs={"flag": InputDef(type=DataType.number, default=True)},
        )
        errors = validate(wf)
        assert "V-024" in _codes(errors)

    def test_any_type_accepts_anything(self):
        wf = _wf(
            inputs={"data": InputDef(type=DataType.any, default=[1, 2, 3])},
        )
        errors = validate(wf)
        assert "V-024" not in _codes(errors)


# ===========================================================================
# V-025: enum only for string/number types
# ===========================================================================


class TestV025EnumValidation:
    def test_valid_string_enum(self):
        wf = _wf(
            inputs={
                "priority": InputDef(type=DataType.string, enum=["low", "high"]),
            },
        )
        errors = validate(wf)
        assert "V-025" not in _codes(errors)

    def test_enum_on_boolean_type(self):
        wf = _wf(
            inputs={
                "flag": InputDef(type=DataType.boolean, enum=[True, False]),
            },
        )
        errors = validate(wf)
        assert "V-025" in _codes(errors)


# ===========================================================================
# V-026: orphan node (no edges)
# ===========================================================================


class TestV026OrphanNode:
    def test_valid(self):
        errors = validate(_valid_wf())
        assert "V-026" not in _codes(errors)

    def test_orphan_node(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="orphan",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-026" in _codes(errors)


# ===========================================================================
# V-027: invalid source handle for node type
# ===========================================================================


class TestV027InvalidHandle:
    def test_valid_default_handle(self):
        errors = validate(_valid_wf())
        assert "V-027" not in _codes(errors)

    def test_invalid_handle_on_http(self):
        wf = _wf(
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
                EdgeDef(id="e2", source="fetch", target="end", source_handle="nonexistent"),
            ],
        )
        errors = validate(wf)
        assert "V-027" in _codes(errors)

    def test_valid_loop_handles(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="loop_node",
                    type=NodeType.loop,
                    config={
                        "items": "{{nodes.start.output.list}}",
                    },
                ),
                NodeDef(
                    id="body_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="loop_node"),
                EdgeDef(id="e2", source="loop_node", target="body_node", source_handle="body"),
                EdgeDef(id="e3", source="loop_node", target="end", source_handle="completed"),
                EdgeDef(id="e4", source="body_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-027" not in _codes(errors)


# ===========================================================================
# V-028: invalid variable reference grammar
# ===========================================================================


class TestV028VariableRefGrammar:
    def test_valid_refs(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "GET",
                        "url": "https://api.example.com/{{workflow.input.order_id}}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="end"),
            ],
            inputs={"order_id": InputDef(type=DataType.string)},
        )
        errors = validate(wf)
        assert "V-028" not in _codes(errors)

    def test_invalid_ref_grammar(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "GET",
                        "url": "https://api.example.com/{{invalid_ref}}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-028" in _codes(errors)


# ===========================================================================
# V-029: variable ref references non-existent node
# ===========================================================================


class TestV029NonExistentNodeRef:
    def test_valid_node_ref(self):
        wf = _wf(
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
                NodeDef(
                    id="process",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                        "inputs": {"val": "{{nodes.fetch.output.body}}"},
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="process"),
                EdgeDef(id="e3", source="process", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-029" not in _codes(errors)

    def test_unknown_node_in_ref(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="process",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                        "inputs": {"val": "{{nodes.nonexistent.output.body}}"},
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="process"),
                EdgeDef(id="e2", source="process", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-029" in _codes(errors)


# ===========================================================================
# V-030: variable ref references non-existent workflow input
# ===========================================================================


class TestV030NonExistentInputRef:
    def test_valid_input_ref(self):
        wf = _wf(
            inputs={"order_id": InputDef(type=DataType.string)},
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "GET",
                        "url": "https://api.example.com/{{workflow.input.order_id}}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-030" not in _codes(errors)

    def test_unknown_workflow_input(self):
        wf = _wf(
            inputs={"order_id": InputDef(type=DataType.string)},
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "GET",
                        "url": "https://api.example.com/{{workflow.input.nonexistent}}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch"),
                EdgeDef(id="e2", source="fetch", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-030" in _codes(errors)


# ===========================================================================
# V-031: http node config schema validation
# ===========================================================================


class TestV031HttpConfigValidation:
    def test_valid_http_config(self):
        wf = _wf(
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
        errors = validate(wf)
        assert "V-031" not in _codes(errors)

    def test_invalid_http_config(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch",
                    type=NodeType.http,
                    config={
                        "method": "INVALID_METHOD",
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
        errors = validate(wf)
        assert "V-031" in _codes(errors)


# ===========================================================================
# V-032: code node config schema validation
# ===========================================================================


class TestV032CodeConfigValidation:
    def test_valid_code_config(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="code_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="code_node"),
                EdgeDef(id="e2", source="code_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-032" not in _codes(errors)

    def test_invalid_code_config_extra_field(self):
        wf = _wf(
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="code_node",
                    type=NodeType.code,
                    config={
                        "language": "python",
                        "source": "return {}",
                        "invalid_field": True,
                    },
                ),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="code_node"),
                EdgeDef(id="e2", source="code_node", target="end"),
            ],
        )
        errors = validate(wf)
        assert "V-032" in _codes(errors)


# ===========================================================================
# Error Aggregation
# ===========================================================================


class TestErrorAggregation:
    def test_multiple_errors_returned(self):
        """Multiple violations in one workflow should all be reported."""
        wf = _wf(
            version="2.0",
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(id="start", type=NodeType.start),  # duplicate
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="end"),
                EdgeDef(id="e1", source="start", target="end"),  # duplicate
            ],
        )
        errors = validate(wf)
        codes = _codes(errors)
        # Should find multiple distinct error codes
        assert "V-001" in codes  # bad version
        assert "V-003" in codes  # duplicate node id
        assert "V-004" in codes  # duplicate edge id

    def test_valid_workflow_no_errors(self):
        """A valid workflow produces zero errors."""
        errors = validate(_valid_wf())
        assert len(errors) == 0


# ===========================================================================
# Full Spec Example
# ===========================================================================


class TestSpecExampleValidation:
    def test_order_approval_is_valid(self):
        """The complete order-approval example from the spec should validate cleanly."""
        wf = _wf(
            inputs={
                "order_id": InputDef(type=DataType.string, required=True),
                "api_token": InputDef(type=DataType.string, required=True),
            },
            outputs={
                "status": OutputDef(type=DataType.string),
                "approved": OutputDef(type=DataType.boolean),
            },
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(
                    id="fetch_order",
                    type=NodeType.http,
                    label="Fetch Order",
                    config={
                        "method": "GET",
                        "url": "https://api.example.com/orders/{{workflow.input.order_id}}",
                        "headers": {"Authorization": "Bearer {{workflow.input.api_token}}"},
                    },
                ),
                NodeDef(
                    id="check_priority",
                    type=NodeType.if_else,
                    label="High Priority?",
                    config={
                        "conditions": [
                            {
                                "id": "is_high",
                                "expression": (
                                    "{{nodes.fetch_order.output.body.priority}} == 'high'"
                                ),
                            },
                        ],
                    },
                ),
                NodeDef(
                    id="approve",
                    type=NodeType.human_input,
                    label="Manager Approval",
                    config={
                        "prompt": "Approve high-priority order {{workflow.input.order_id}}?",
                        "input_schema": {
                            "approved": {"type": "boolean", "required": True},
                            "comment": {"type": "string"},
                        },
                    },
                ),
                NodeDef(
                    id="auto_approve",
                    type=NodeType.code,
                    label="Auto Approve",
                    config={
                        "language": "python",
                        "source": "return {'approved': True,"
                        " 'comment': 'Auto-approved (normal priority)'}",
                        "inputs": {},
                    },
                ),
                NodeDef(
                    id="end",
                    type=NodeType.end,
                    config={
                        "output_mapping": {
                            "status": "completed",
                            "approved": "{{nodes.approve.output.approved}}",
                        },
                    },
                ),
            ],
            edges=[
                EdgeDef(id="e1", source="start", target="fetch_order"),
                EdgeDef(id="e2", source="fetch_order", target="check_priority"),
                EdgeDef(
                    id="e3", source="check_priority", target="approve", source_handle="is_high"
                ),
                EdgeDef(
                    id="e4", source="check_priority", target="auto_approve", source_handle="else"
                ),
                EdgeDef(id="e5", source="approve", target="end"),
                EdgeDef(id="e6", source="auto_approve", target="end"),
            ],
        )
        errors = validate(wf)
        assert errors == [], f"Expected no errors, got: {errors}"
