"""Scoped variable storage and reference resolution for workflow runs.

This module is pure Python with zero external dependencies.
"""

from __future__ import annotations

import copy
import re
from typing import Any

# Matches: {{workflow.input.KEY}} or {{nodes.NODE_ID.output.KEY}}
_REF_PATTERN = re.compile(r"^\{\{(workflow\.input\.(\w+)|nodes\.(\w+)\.output\.(\w+))\}\}$")


class VariablePool:
    """Scoped key-value store for a single workflow run.

    Two scopes:
    - **workflow inputs**: Readable by any node.
    - **node outputs**: Keyed by *node_id*, each node stores a dict of outputs.

    Backed by a JSONB column on the ``workflow_runs`` table.  Loaded into
    memory during node execution, flushed to DB after each node completes.
    """

    def __init__(self, workflow_inputs: dict[str, Any] | None = None) -> None:
        self._workflow_inputs: dict[str, Any] = dict(workflow_inputs) if workflow_inputs else {}
        self._node_outputs: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Workflow inputs
    # ------------------------------------------------------------------

    def set_workflow_inputs(self, inputs: dict[str, Any]) -> None:
        """Replace the workflow input values."""
        self._workflow_inputs = dict(inputs)

    def get_workflow_input(self, key: str) -> Any:
        """Return a single workflow input value.

        Raises ``KeyError`` if *key* is not present.
        """
        try:
            return self._workflow_inputs[key]
        except KeyError:
            raise KeyError(f"Workflow input {key!r} not found") from None

    # ------------------------------------------------------------------
    # Node outputs
    # ------------------------------------------------------------------

    def set_node_outputs(self, node_id: str, outputs: dict[str, Any]) -> None:
        """Store (replace) outputs for *node_id*."""
        self._node_outputs[node_id] = dict(outputs)

    def get_node_output(self, node_id: str, key: str) -> Any:
        """Return a single output value for *node_id*.

        Raises ``KeyError`` if *node_id* or *key* is not present.
        """
        try:
            node = self._node_outputs[node_id]
        except KeyError:
            raise KeyError(f"Node {node_id!r} has no recorded outputs") from None
        try:
            return node[key]
        except KeyError:
            raise KeyError(f"Node {node_id!r} has no output {key!r}") from None

    def get_node_outputs(self, node_id: str) -> dict[str, Any]:
        """Return the full outputs dict for *node_id*.

        Raises ``KeyError`` if *node_id* is not present.
        """
        try:
            return self._node_outputs[node_id]
        except KeyError:
            raise KeyError(f"Node {node_id!r} has no recorded outputs") from None

    # ------------------------------------------------------------------
    # Reference resolution
    # ------------------------------------------------------------------

    def resolve_reference(self, ref: str) -> Any:
        """Resolve a ``{{...}}`` reference string to its value.

        Supported patterns:
        - ``{{workflow.input.KEY}}`` → ``get_workflow_input(KEY)``
        - ``{{nodes.NODE_ID.output.KEY}}`` → ``get_node_output(NODE_ID, KEY)``

        Returns *ref* unchanged if it doesn't match the reference pattern.
        """
        m = _REF_PATTERN.match(ref)
        if m is None:
            return ref

        workflow_key = m.group(2)
        if workflow_key is not None:
            return self.get_workflow_input(workflow_key)

        node_id = m.group(3)
        output_key = m.group(4)
        return self.get_node_output(node_id, output_key)

    def resolve_value(self, value: Any) -> Any:
        """Recursively resolve references within an arbitrary value.

        - **str** containing ``{{...}}`` → :meth:`resolve_reference`
        - **dict** → recursively resolve all values
        - **list** → recursively resolve all items
        - Everything else → returned as-is
        """
        if isinstance(value, str):
            if "{{" in value and "}}" in value:
                return self.resolve_reference(value)
            return value
        if isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        return value

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for JSONB storage."""
        return {
            "workflow_inputs": copy.deepcopy(self._workflow_inputs),
            "node_outputs": copy.deepcopy(self._node_outputs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VariablePool:
        """Deserialize from a stored dict."""
        pool = cls(workflow_inputs=copy.deepcopy(data.get("workflow_inputs", {})))
        for node_id, outputs in copy.deepcopy(data.get("node_outputs", {})).items():
            pool._node_outputs[node_id] = outputs
        return pool
