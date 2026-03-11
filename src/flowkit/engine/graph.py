"""Executable graph representation built from a WorkflowDefinition."""

from __future__ import annotations

from collections import defaultdict, deque

from flowkit.definition.schema import EdgeDef, NodeDef, NodeType, WorkflowDefinition


class Graph:
    """In-memory graph built from a WorkflowDefinition for runtime use."""

    def __init__(self, definition: WorkflowDefinition) -> None:
        self._nodes: dict[str, NodeDef] = {n.id: n for n in definition.nodes}
        self._edges: list[EdgeDef] = list(definition.edges)

        self._outgoing: dict[str, list[EdgeDef]] = defaultdict(list)
        self._incoming: dict[str, list[EdgeDef]] = defaultdict(list)

        for edge in self._edges:
            self._outgoing[edge.source].append(edge)
            self._incoming[edge.target].append(edge)

    def get_start_node(self) -> NodeDef:
        for node in self._nodes.values():
            if node.type == NodeType.start:
                return node
        raise ValueError("No start node found in workflow")

    def get_end_node(self) -> NodeDef:
        for node in self._nodes.values():
            if node.type == NodeType.end:
                return node
        raise ValueError("No end node found in workflow")

    def get_node(self, node_id: str) -> NodeDef:
        try:
            return self._nodes[node_id]
        except KeyError:
            raise KeyError(f"Node {node_id!r} not found") from None

    def get_outgoing_edges(self, node_id: str, handle: str = "default") -> list[EdgeDef]:
        return [e for e in self._outgoing.get(node_id, []) if e.source_handle == handle]

    def get_incoming_edges(self, node_id: str) -> list[EdgeDef]:
        return list(self._incoming.get(node_id, []))

    def get_successors(self, node_id: str, handle: str | None = None) -> list[str]:
        edges = self._outgoing.get(node_id, [])
        if handle is not None:
            edges = [e for e in edges if e.source_handle == handle]
        return [e.target for e in edges]

    def get_predecessors(self, node_id: str) -> list[str]:
        return [e.source for e in self._incoming.get(node_id, [])]

    def find_ready_nodes(self, completed_nodes: set[str]) -> list[str]:
        """Find nodes whose ALL predecessors are completed and aren't completed themselves."""
        ready = []
        for node_id, node_def in self._nodes.items():
            if node_id in completed_nodes:
                continue

            predecessors = self.get_predecessors(node_id)
            if not predecessors and node_id not in completed_nodes:
                ready.append(node_id)
            elif all(p in completed_nodes for p in predecessors):
                ready.append(node_id)

        return ready

    def topological_order(self) -> list[str]:
        """Return nodes in topological order via Kahn's algorithm."""
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        for edge in self._edges:
            in_degree[edge.target] += 1

        queue: deque[str] = deque()
        for nid, deg in in_degree.items():
            if deg == 0:
                queue.append(nid)

        result: list[str] = []
        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            for edge in self._outgoing.get(node_id, []):
                in_degree[edge.target] -= 1
                if in_degree[edge.target] == 0:
                    queue.append(edge.target)

        return result
