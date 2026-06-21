"""Flowkit DSL v1 — Graph Validator.

Validates a WorkflowDefinition against all structural, graph, type, and
semantic rules defined in the DSL v1 specification.

Usage:
    errors = validate(definition)
    if errors:
        for e in errors:
            print(f"[{e.code}] {e.message}")
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from flowkit.definition.schema import (
    CodeNodeConfig,
    DataType,
    HttpNodeConfig,
    IfElseConfig,
    NodeDef,
    NodeType,
    SubWorkflowConfig,
    WorkflowDefinition,
)

# ---------------------------------------------------------------------------
# Validation Error
# ---------------------------------------------------------------------------

VARIABLE_REF_PATTERN = re.compile(
    r"\{\{(workflow\.input\.[a-zA-Z_][a-zA-Z0-9_]*"
    r"|workflow\.output\.[a-zA-Z_][a-zA-Z0-9_]*"
    r"|nodes\.[a-zA-Z_][a-zA-Z0-9_]*\.output(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\}\}"
)

# Finds all {{...}} patterns in a string (for checking grammar compliance).
ALL_TEMPLATE_PATTERN = re.compile(r"\{\{(.*?)\}\}")

NODE_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class ValidationError:
    """A single validation error or warning."""

    code: str
    message: str
    node_id: str | None = field(default=None)
    edge_id: str | None = field(default=None)


# ---------------------------------------------------------------------------
# Valid handles per node type
# ---------------------------------------------------------------------------

_VALID_SOURCE_HANDLES: dict[NodeType, set[str] | None] = {
    NodeType.start: {"default"},
    NodeType.end: None,  # end has no outgoing edges
    NodeType.http: {"default"},
    NodeType.code: {"default"},
    NodeType.if_else: None,  # dynamic: condition ids + "else"
    NodeType.loop: {"body", "completed"},
    NodeType.human_input: {"default"},
    NodeType.parallel: {"default"},
    NodeType.sub_workflow: {"default"},
}


def _get_valid_source_handles(node: NodeDef) -> set[str] | None:
    """Return the set of valid source handles for a node, or None if dynamic."""
    if node.type == NodeType.if_else and node.config:
        try:
            cfg = IfElseConfig.model_validate(node.config)
            return {c.id for c in cfg.conditions} | {"else"}
        except Exception:
            return {"else"}
    return _VALID_SOURCE_HANDLES.get(node.type)


# ---------------------------------------------------------------------------
# Helper: extract all {{...}} references from a value
# ---------------------------------------------------------------------------


def _extract_refs_from_value(value: Any) -> list[str]:
    """Extract all template references from a string or nested structure."""
    refs: list[str] = []
    if isinstance(value, str):
        refs.extend(ALL_TEMPLATE_PATTERN.findall(value))
    elif isinstance(value, dict):
        for v in value.values():
            refs.extend(_extract_refs_from_value(v))
    elif isinstance(value, list):
        for v in value:
            refs.extend(_extract_refs_from_value(v))
    return refs


def _extract_all_refs_from_config(config: dict[str, Any] | None) -> list[str]:
    """Extract all template references from a node config dict."""
    if config is None:
        return []
    return _extract_refs_from_value(config)


# ---------------------------------------------------------------------------
# Type check helper for V-024
# ---------------------------------------------------------------------------

_TYPE_CHECKERS: dict[DataType, type | tuple[type, ...]] = {
    DataType.string: str,
    DataType.number: (int, float),
    DataType.boolean: bool,
    DataType.object: dict,
    DataType.array: list,
}


# ---------------------------------------------------------------------------
# Main Validation Function
# ---------------------------------------------------------------------------


def validate(definition: WorkflowDefinition) -> list[ValidationError]:
    """Validate a WorkflowDefinition against all DSL v1 rules.

    Returns a list of ValidationError instances (empty if valid).
    Errors are collected exhaustively — multiple issues reported together.
    """
    errors: list[ValidationError] = []

    # Build indexes
    node_map: dict[str, NodeDef] = {n.id: n for n in definition.nodes}
    node_ids = set(node_map.keys())
    edge_ids: set[str] = set()

    # Adjacency for graph analysis
    outgoing: dict[str, list[str]] = defaultdict(list)  # node_id -> [target_ids]
    incoming: dict[str, list[str]] = defaultdict(list)  # node_id -> [source_ids]
    outgoing_edges: dict[str, list[Any]] = defaultdict(list)  # node_id -> [edge]
    incoming_edges: dict[str, list[Any]] = defaultdict(list)

    # -----------------------------------------------------------------------
    # V-001: version must be "1.0"
    # -----------------------------------------------------------------------
    if definition.version != "1.0":
        errors.append(
            ValidationError(
                code="V-001",
                message=f"Version must be '1.0', got '{definition.version}'",
            )
        )

    # -----------------------------------------------------------------------
    # V-002: at least 2 nodes
    # -----------------------------------------------------------------------
    if len(definition.nodes) < 2:
        errors.append(
            ValidationError(
                code="V-002",
                message=f"Workflow must have at least 2 nodes, got {len(definition.nodes)}",
            )
        )

    # -----------------------------------------------------------------------
    # V-003: all node IDs unique
    # -----------------------------------------------------------------------
    seen_node_ids: set[str] = set()
    for node in definition.nodes:
        if node.id in seen_node_ids:
            errors.append(
                ValidationError(
                    code="V-003",
                    message=f"Duplicate node id '{node.id}'",
                    node_id=node.id,
                )
            )
        seen_node_ids.add(node.id)

    # -----------------------------------------------------------------------
    # V-004: all edge IDs unique
    # -----------------------------------------------------------------------
    for edge in definition.edges:
        if edge.id in edge_ids:
            errors.append(
                ValidationError(
                    code="V-004",
                    message=f"Duplicate edge id '{edge.id}'",
                    edge_id=edge.id,
                )
            )
        edge_ids.add(edge.id)

    # -----------------------------------------------------------------------
    # V-005: edge source/target reference existing nodes
    # -----------------------------------------------------------------------
    for edge in definition.edges:
        if edge.source not in node_ids:
            errors.append(
                ValidationError(
                    code="V-005",
                    message=f"Edge '{edge.id}' source '{edge.source}' references unknown node",
                    edge_id=edge.id,
                )
            )
        if edge.target not in node_ids:
            errors.append(
                ValidationError(
                    code="V-005",
                    message=f"Edge '{edge.id}' target '{edge.target}' references unknown node",
                    edge_id=edge.id,
                )
            )
        # Build adjacency only for valid refs
        if edge.source in node_ids and edge.target in node_ids:
            outgoing[edge.source].append(edge.target)
            incoming[edge.target].append(edge.source)
            outgoing_edges[edge.source].append(edge)
            incoming_edges[edge.target].append(edge)

    # -----------------------------------------------------------------------
    # V-006: no self-loops
    # -----------------------------------------------------------------------
    for edge in definition.edges:
        if edge.source == edge.target:
            errors.append(
                ValidationError(
                    code="V-006",
                    message=f"Edge '{edge.id}' is a self-loop on node '{edge.source}'",
                    edge_id=edge.id,
                    node_id=edge.source,
                )
            )

    # -----------------------------------------------------------------------
    # V-007: exactly one start node
    # -----------------------------------------------------------------------
    start_nodes = [n for n in definition.nodes if n.type == NodeType.start]
    if len(start_nodes) == 0:
        errors.append(
            ValidationError(
                code="V-007",
                message="Workflow must have exactly one 'start' node, found 0",
            )
        )
    elif len(start_nodes) > 1:
        errors.append(
            ValidationError(
                code="V-007",
                message=f"Workflow must have exactly one 'start' node, found {len(start_nodes)}",
            )
        )

    # -----------------------------------------------------------------------
    # V-008: exactly one end node
    # -----------------------------------------------------------------------
    end_nodes = [n for n in definition.nodes if n.type == NodeType.end]
    if len(end_nodes) == 0:
        errors.append(
            ValidationError(
                code="V-008",
                message="Workflow must have exactly one 'end' node, found 0",
            )
        )
    elif len(end_nodes) > 1:
        errors.append(
            ValidationError(
                code="V-008",
                message=f"Workflow must have exactly one 'end' node, found {len(end_nodes)}",
            )
        )

    # -----------------------------------------------------------------------
    # V-009: start node has 0 incoming edges
    # -----------------------------------------------------------------------
    if len(start_nodes) == 1:
        start_id = start_nodes[0].id
        if incoming[start_id]:
            errors.append(
                ValidationError(
                    code="V-009",
                    message=f"Start node '{start_id}' must have 0 incoming edges, "
                    f"has {len(incoming[start_id])}",
                    node_id=start_id,
                )
            )

    # -----------------------------------------------------------------------
    # V-010: start node has exactly 1 outgoing edge
    # -----------------------------------------------------------------------
    if len(start_nodes) == 1:
        start_id = start_nodes[0].id
        start_out = outgoing_edges.get(start_id, [])
        if len(start_out) != 1:
            errors.append(
                ValidationError(
                    code="V-010",
                    message=f"Start node '{start_id}' must have exactly 1 outgoing edge, "
                    f"has {len(start_out)}",
                    node_id=start_id,
                )
            )

    # -----------------------------------------------------------------------
    # V-011: end node has 0 outgoing edges
    # -----------------------------------------------------------------------
    if len(end_nodes) == 1:
        end_id = end_nodes[0].id
        if outgoing[end_id]:
            errors.append(
                ValidationError(
                    code="V-011",
                    message=f"End node '{end_id}' must have 0 outgoing edges, "
                    f"has {len(outgoing[end_id])}",
                    node_id=end_id,
                )
            )

    # -----------------------------------------------------------------------
    # V-012: end node has ≥1 incoming edges
    # -----------------------------------------------------------------------
    if len(end_nodes) == 1:
        end_id = end_nodes[0].id
        if not incoming[end_id]:
            errors.append(
                ValidationError(
                    code="V-012",
                    message=f"End node '{end_id}' must have at least 1 incoming edge",
                    node_id=end_id,
                )
            )

    # -----------------------------------------------------------------------
    # V-013: graph is a DAG (no cycles) — Kahn's algorithm
    # -----------------------------------------------------------------------
    if node_ids:
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in definition.edges:
            if (
                edge.source in node_ids
                and edge.target in node_ids
                # Skip self-loops for DAG check
                and edge.source != edge.target
            ):
                adj[edge.source].append(edge.target)
                in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        queue: deque[str] = deque()
        for nid in node_ids:
            if in_degree[nid] == 0:
                queue.append(nid)

        topo_count = 0
        while queue:
            node_id = queue.popleft()
            topo_count += 1
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if topo_count < len(node_ids):
            errors.append(
                ValidationError(
                    code="V-013",
                    message="Graph contains a cycle (not a DAG)",
                )
            )

    # -----------------------------------------------------------------------
    # V-014: all nodes reachable from start
    # -----------------------------------------------------------------------
    if len(start_nodes) == 1:
        start_id = start_nodes[0].id
        visited: set[str] = set()
        bfs_queue: deque[str] = deque([start_id])
        while bfs_queue:
            current = bfs_queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in outgoing.get(current, []):
                if neighbor not in visited:
                    bfs_queue.append(neighbor)
        unreachable = node_ids - visited
        for nid in sorted(unreachable):
            errors.append(
                ValidationError(
                    code="V-014",
                    message=f"Node '{nid}' is not reachable from start",
                    node_id=nid,
                )
            )

    # -----------------------------------------------------------------------
    # V-015: end node reachable from every non-end node
    # -----------------------------------------------------------------------
    if len(end_nodes) == 1:
        end_id = end_nodes[0].id
        # BFS backwards from end using reverse edges
        reverse_visited: set[str] = set()
        rev_queue: deque[str] = deque([end_id])
        while rev_queue:
            current = rev_queue.popleft()
            if current in reverse_visited:
                continue
            reverse_visited.add(current)
            for src in incoming.get(current, []):
                if src not in reverse_visited:
                    rev_queue.append(src)
        for nid in sorted(node_ids):
            node = node_map[nid]
            if node.type != NodeType.end and nid not in reverse_visited:
                errors.append(
                    ValidationError(
                        code="V-015",
                        message=f"End node not reachable from node '{nid}'",
                        node_id=nid,
                    )
                )

    # -----------------------------------------------------------------------
    # V-016: node ID matches pattern [a-z0-9_]+
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if not NODE_ID_PATTERN.match(node.id):
            errors.append(
                ValidationError(
                    code="V-016",
                    message=f"Node id '{node.id}' does not match [a-z0-9_]+",
                    node_id=node.id,
                )
            )

    # -----------------------------------------------------------------------
    # V-017: every if_else condition has matching edge with source_handle = condition.id
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.if_else and node.config:
            try:
                cfg = IfElseConfig.model_validate(node.config)
            except Exception:
                continue
            node_outgoing_handles = {e.source_handle for e in outgoing_edges.get(node.id, [])}
            for cond in cfg.conditions:
                if cond.id not in node_outgoing_handles:
                    errors.append(
                        ValidationError(
                            code="V-017",
                            message=f"if_else node '{node.id}' condition '{cond.id}' "
                            f"has no matching edge with source_handle='{cond.id}'",
                            node_id=node.id,
                        )
                    )

    # -----------------------------------------------------------------------
    # V-018: if_else must have 'else' handle edge
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.if_else:
            node_outgoing_handles = {e.source_handle for e in outgoing_edges.get(node.id, [])}
            if "else" not in node_outgoing_handles:
                errors.append(
                    ValidationError(
                        code="V-018",
                        message=f"if_else node '{node.id}' must have an 'else' handle edge",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-019: loop must have 'body' and 'completed' handle edges
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.loop:
            node_outgoing_handles = {e.source_handle for e in outgoing_edges.get(node.id, [])}
            if "body" not in node_outgoing_handles:
                errors.append(
                    ValidationError(
                        code="V-019",
                        message=f"loop node '{node.id}' must have a 'body' handle edge",
                        node_id=node.id,
                    )
                )
            if "completed" not in node_outgoing_handles:
                errors.append(
                    ValidationError(
                        code="V-019",
                        message=f"loop node '{node.id}' must have a 'completed' handle edge",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-020: http url must be non-empty
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.http and node.config:
            url = node.config.get("url", "")
            if not url or (isinstance(url, str) and not url.strip()):
                errors.append(
                    ValidationError(
                        code="V-020",
                        message=f"http node '{node.id}' must have a non-empty url",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-021: code source must be non-empty
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.code and node.config:
            source = node.config.get("source", "")
            if not source or (isinstance(source, str) and not source.strip()):
                errors.append(
                    ValidationError(
                        code="V-021",
                        message=f"code node '{node.id}' must have non-empty source",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-022: code language must be 'python'
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.code and node.config:
            lang = node.config.get("language", "")
            if lang != "python":
                errors.append(
                    ValidationError(
                        code="V-022",
                        message=f"code node '{node.id}' language must be 'python', got '{lang}'",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-023: human_input prompt non-empty
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.human_input and node.config:
            prompt = node.config.get("prompt", "")
            if not prompt or (isinstance(prompt, str) and not prompt.strip()):
                errors.append(
                    ValidationError(
                        code="V-023",
                        message=f"human_input node '{node.id}' must have a non-empty prompt",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-024: input type mismatch — default values must match declared types
    # -----------------------------------------------------------------------
    for name, inp in definition.inputs.items():
        if inp.default is not None and inp.type != DataType.any:
            checker = _TYPE_CHECKERS.get(inp.type)
            if checker is not None:
                # Special case: bool is subclass of int in Python
                if inp.type == DataType.number and isinstance(inp.default, bool):
                    errors.append(
                        ValidationError(
                            code="V-024",
                            message=f"Input '{name}' default value type mismatch: "
                            f"expected {inp.type.value}, got boolean",
                        )
                    )
                elif not isinstance(inp.default, checker):
                    errors.append(
                        ValidationError(
                            code="V-024",
                            message=f"Input '{name}' default value type mismatch: "
                            f"expected {inp.type.value}, got {type(inp.default).__name__}",
                        )
                    )

    # -----------------------------------------------------------------------
    # V-025: enum values must match declared type
    # -----------------------------------------------------------------------
    for name, inp in definition.inputs.items():
        if inp.enum is not None and inp.type not in (
            DataType.string,
            DataType.number,
            DataType.any,
        ):
            errors.append(
                ValidationError(
                    code="V-025",
                    message=f"Input '{name}' enum is only allowed for string/number types",
                )
            )

    # -----------------------------------------------------------------------
    # V-026: orphan node — every node must have at least one edge
    # -----------------------------------------------------------------------
    if len(definition.nodes) > 2 or (len(definition.nodes) == 2 and not definition.edges):
        nodes_with_edges: set[str] = set()
        for edge in definition.edges:
            nodes_with_edges.add(edge.source)
            nodes_with_edges.add(edge.target)
        for node in definition.nodes:
            if node.id not in nodes_with_edges:
                errors.append(
                    ValidationError(
                        code="V-026",
                        message=f"Node '{node.id}' is an orphan (no edges)",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-027: invalid source handle for node type
    # -----------------------------------------------------------------------
    for edge in definition.edges:
        if edge.source in node_map:
            node = node_map[edge.source]
            valid_handles = _get_valid_source_handles(node)
            if valid_handles is not None and edge.source_handle not in valid_handles:
                errors.append(
                    ValidationError(
                        code="V-027",
                        message=f"Edge '{edge.id}' has invalid source_handle "
                        f"'{edge.source_handle}' for node type '{node.type.value}'",
                        edge_id=edge.id,
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-028: invalid variable reference grammar
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        refs = _extract_all_refs_from_config(node.config)
        for ref in refs:
            full_ref = "{{" + ref + "}}"
            if not VARIABLE_REF_PATTERN.match(full_ref):
                errors.append(
                    ValidationError(
                        code="V-028",
                        message=f"Node '{node.id}' has invalid variable reference '{full_ref}'",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-029: variable ref references non-existent node
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        refs = _extract_all_refs_from_config(node.config)
        for ref in refs:
            full_ref = "{{" + ref + "}}"
            if VARIABLE_REF_PATTERN.match(full_ref) and ref.startswith("nodes."):
                parts = ref.split(".")
                if len(parts) >= 2:
                    ref_node_id = parts[1]
                    if ref_node_id not in node_ids:
                        errors.append(
                            ValidationError(
                                code="V-029",
                                message=f"Node '{node.id}' references unknown node "
                                f"'{ref_node_id}' in variable reference",
                                node_id=node.id,
                            )
                        )

    # -----------------------------------------------------------------------
    # V-030: variable ref references non-existent workflow input
    # -----------------------------------------------------------------------
    input_names = set(definition.inputs.keys())
    for node in definition.nodes:
        refs = _extract_all_refs_from_config(node.config)
        for ref in refs:
            full_ref = "{{" + ref + "}}"
            if VARIABLE_REF_PATTERN.match(full_ref) and ref.startswith("workflow.input."):
                parts = ref.split(".")
                if len(parts) >= 3:
                    ref_input = parts[2]
                    if ref_input not in input_names and input_names:
                        errors.append(
                            ValidationError(
                                code="V-030",
                                message=f"Node '{node.id}' references unknown workflow input "
                                f"'{ref_input}'",
                                node_id=node.id,
                            )
                        )

    # -----------------------------------------------------------------------
    # V-031: http node config validation
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.http and node.config:
            try:
                HttpNodeConfig.model_validate(node.config)
            except Exception as exc:
                errors.append(
                    ValidationError(
                        code="V-031",
                        message=f"http node '{node.id}' has invalid config: {exc}",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-032: code node config validation
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.code and node.config:
            try:
                CodeNodeConfig.model_validate(node.config)
            except Exception as exc:
                errors.append(
                    ValidationError(
                        code="V-032",
                        message=f"code node '{node.id}' has invalid config: {exc}",
                        node_id=node.id,
                    )
                )

    # -----------------------------------------------------------------------
    # V-033: sub_workflow node config validation
    # -----------------------------------------------------------------------
    for node in definition.nodes:
        if node.type == NodeType.sub_workflow and node.config:
            try:
                SubWorkflowConfig.model_validate(node.config)
            except Exception as exc:
                errors.append(
                    ValidationError(
                        code="V-033",
                        message=f"sub_workflow node '{node.id}' has invalid config: {exc}",
                        node_id=node.id,
                    )
                )

    return errors
