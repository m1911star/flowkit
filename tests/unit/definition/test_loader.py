"""Tests for flowkit.definition.loader — load, load_dict, compute_checksum."""

from __future__ import annotations

import json

import pytest

from flowkit.definition.loader import (
    DefinitionLoadError,
    compute_checksum,
    load,
    load_dict,
)
from flowkit.definition.schema import WorkflowDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_VALID: dict = {
    "version": "1.0",
    "metadata": {"name": "test-wf"},
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "end"},
    ],
}

ORDER_APPROVAL: dict = {
    "version": "1.0",
    "metadata": {
        "name": "order-approval",
        "description": "Fetch order, check priority, route to approval if high",
    },
    "inputs": {
        "order_id": {"type": "string", "required": True},
        "api_token": {"type": "string", "required": True},
    },
    "outputs": {
        "status": {"type": "string"},
        "approved": {"type": "boolean"},
    },
    "nodes": [
        {"id": "start", "type": "start"},
        {
            "id": "fetch_order",
            "type": "http",
            "label": "Fetch Order",
            "config": {
                "method": "GET",
                "url": "https://api.example.com/orders/{{workflow.input.order_id}}",
                "headers": {"Authorization": "Bearer {{workflow.input.api_token}}"},
            },
        },
        {
            "id": "check_priority",
            "type": "if_else",
            "label": "High Priority?",
            "config": {
                "conditions": [
                    {
                        "id": "is_high",
                        "expression": "{{nodes.fetch_order.output.body.priority}} == 'high'",
                    }
                ]
            },
        },
        {
            "id": "approve",
            "type": "human_input",
            "label": "Manager Approval",
            "config": {
                "prompt": "Approve high-priority order {{workflow.input.order_id}}?",
                "input_schema": {
                    "approved": {"type": "boolean", "required": True},
                    "comment": {"type": "string"},
                },
            },
        },
        {
            "id": "auto_approve",
            "type": "code",
            "label": "Auto Approve",
            "config": {
                "language": "python",
                "source": "return {'approved': True, 'comment': 'Auto-approved (normal priority)'}",
                "inputs": {},
            },
        },
        {
            "id": "end",
            "type": "end",
            "config": {
                "output_mapping": {
                    "status": "completed",
                    "approved": "{{nodes.approve.output.approved}}",
                }
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "fetch_order"},
        {"id": "e2", "source": "fetch_order", "target": "check_priority"},
        {
            "id": "e3",
            "source": "check_priority",
            "target": "approve",
            "source_handle": "is_high",
        },
        {
            "id": "e4",
            "source": "check_priority",
            "target": "auto_approve",
            "source_handle": "else",
        },
        {"id": "e5", "source": "approve", "target": "end"},
        {"id": "e6", "source": "auto_approve", "target": "end"},
    ],
}


# ===========================================================================
# load() from JSON string
# ===========================================================================


class TestLoad:
    def test_minimal_valid(self):
        wf = load(json.dumps(MINIMAL_VALID))
        assert isinstance(wf, WorkflowDefinition)
        assert wf.version == "1.0"
        assert wf.metadata.name == "test-wf"

    def test_order_approval(self):
        wf = load(json.dumps(ORDER_APPROVAL))
        assert wf.metadata.name == "order-approval"
        assert len(wf.nodes) == 6

    def test_invalid_json(self):
        with pytest.raises(DefinitionLoadError, match="Invalid JSON") as exc_info:
            load("{not valid json}")
        assert len(exc_info.value.parse_errors) > 0

    def test_json_array_not_object(self):
        with pytest.raises(DefinitionLoadError, match="Expected a JSON object"):
            load("[1, 2, 3]")

    def test_schema_validation_error(self):
        bad = {**MINIMAL_VALID, "version": "2.0"}
        with pytest.raises(DefinitionLoadError, match="Schema validation failed"):
            load(json.dumps(bad))

    def test_graph_validation_error(self):
        """Valid schema but invalid graph (cycle)."""
        data = {
            "version": "1.0",
            "metadata": {"name": "cycle-wf"},
            "nodes": [
                {"id": "start", "type": "start"},
                {
                    "id": "a",
                    "type": "code",
                    "config": {"language": "python", "source": "return {}"},
                },
                {
                    "id": "b",
                    "type": "code",
                    "config": {"language": "python", "source": "return {}"},
                },
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "a"},
                {"id": "e2", "source": "a", "target": "b"},
                {"id": "e3", "source": "b", "target": "a"},
                {"id": "e4", "source": "b", "target": "end"},
            ],
        }
        with pytest.raises(DefinitionLoadError, match="Validation failed") as exc_info:
            load(json.dumps(data))
        assert len(exc_info.value.validation_errors) > 0
        codes = {e.code for e in exc_info.value.validation_errors}
        assert "V-013" in codes  # cycle detected

    def test_parse_errors_on_schema_failure(self):
        """Parse errors list is populated on Pydantic failure."""
        bad = {"version": "1.0"}  # missing metadata, nodes, edges
        with pytest.raises(DefinitionLoadError) as exc_info:
            load(json.dumps(bad))
        assert len(exc_info.value.parse_errors) > 0


# ===========================================================================
# load_dict() from dict
# ===========================================================================


class TestLoadDict:
    def test_minimal_valid(self):
        wf = load_dict(MINIMAL_VALID)
        assert isinstance(wf, WorkflowDefinition)

    def test_missing_required_field(self):
        with pytest.raises(DefinitionLoadError, match="Schema validation"):
            load_dict({"version": "1.0", "metadata": {"name": "x"}})

    def test_validation_errors_populated(self):
        """Validation errors include multiple issues."""
        data = {
            "version": "1.0",
            "metadata": {"name": "bad-wf"},
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "start", "type": "start"},  # dup
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "end"},
            ],
        }
        with pytest.raises(DefinitionLoadError) as exc_info:
            load_dict(data)
        assert len(exc_info.value.validation_errors) >= 1


# ===========================================================================
# Round-trip: JSON → definition → dict → JSON
# ===========================================================================


class TestRoundTrip:
    def test_json_roundtrip(self):
        """JSON string → load → dump → load produces identical definition."""
        json_str = json.dumps(MINIMAL_VALID)
        wf1 = load(json_str)

        dumped = wf1.model_dump(mode="json")
        wf2 = load_dict(dumped)

        assert wf1 == wf2

    def test_order_approval_roundtrip(self):
        wf1 = load(json.dumps(ORDER_APPROVAL))
        dumped = wf1.model_dump(mode="json")
        wf2 = load_dict(dumped)
        assert wf1 == wf2

    def test_dict_roundtrip_preserves_all_fields(self):
        wf = load_dict(ORDER_APPROVAL)
        d = wf.model_dump(mode="json")

        assert d["version"] == "1.0"
        assert d["metadata"]["name"] == "order-approval"
        assert "order_id" in d["inputs"]
        assert "status" in d["outputs"]
        assert len(d["nodes"]) == 6
        assert len(d["edges"]) == 6


# ===========================================================================
# compute_checksum
# ===========================================================================


class TestComputeChecksum:
    def test_deterministic(self):
        """Same definition always produces same checksum."""
        wf = load_dict(MINIMAL_VALID)
        c1 = compute_checksum(wf)
        c2 = compute_checksum(wf)
        assert c1 == c2

    def test_hex_string_format(self):
        wf = load_dict(MINIMAL_VALID)
        checksum = compute_checksum(wf)
        # SHA-256 hex digest is 64 chars
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_different_definitions_different_checksums(self):
        wf1 = load_dict(MINIMAL_VALID)
        wf2 = load_dict(ORDER_APPROVAL)
        assert compute_checksum(wf1) != compute_checksum(wf2)

    def test_checksum_stable_across_dict_ordering(self):
        """Checksum doesn't depend on Python dict insertion order."""
        # Build two dicts with different insertion orders
        data_a = {
            "version": "1.0",
            "metadata": {"name": "test-wf"},
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "end", "type": "end"},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "end"},
            ],
        }
        data_b = {
            "edges": [
                {"id": "e1", "target": "end", "source": "start"},
            ],
            "nodes": [
                {"type": "start", "id": "start"},
                {"type": "end", "id": "end"},
            ],
            "metadata": {"name": "test-wf"},
            "version": "1.0",
        }
        wf_a = load_dict(data_a)
        wf_b = load_dict(data_b)
        assert compute_checksum(wf_a) == compute_checksum(wf_b)

    def test_order_approval_checksum(self):
        wf = load_dict(ORDER_APPROVAL)
        checksum = compute_checksum(wf)
        # Re-load and recompute
        wf2 = load(json.dumps(ORDER_APPROVAL))
        assert compute_checksum(wf2) == checksum


# ===========================================================================
# DefinitionLoadError structure
# ===========================================================================


class TestDefinitionLoadError:
    def test_error_message(self):
        err = DefinitionLoadError("test error")
        assert str(err) == "test error"
        assert err.parse_errors == []
        assert err.validation_errors == []

    def test_with_parse_errors(self):
        err = DefinitionLoadError(
            "parse failed",
            parse_errors=[{"error": "bad json"}],
        )
        assert len(err.parse_errors) == 1

    def test_with_validation_errors(self):
        from flowkit.definition.validator import ValidationError

        verr = ValidationError(code="V-001", message="bad version")
        err = DefinitionLoadError(
            "validation failed",
            validation_errors=[verr],
        )
        assert len(err.validation_errors) == 1
        assert err.validation_errors[0].code == "V-001"
