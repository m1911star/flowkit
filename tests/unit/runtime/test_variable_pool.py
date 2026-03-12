"""Tests for flowkit.runtime.variable_pool — scoped variable storage + reference resolution."""

import pytest

from flowkit.runtime.variable_pool import VariablePool

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_empty(self):
        pool = VariablePool()
        assert pool.to_dict() == {"workflow_inputs": {}, "node_outputs": {}}

    def test_with_workflow_inputs(self):
        pool = VariablePool(workflow_inputs={"order_id": "abc123"})
        assert pool.get_workflow_input("order_id") == "abc123"


# ---------------------------------------------------------------------------
# Workflow inputs
# ---------------------------------------------------------------------------


class TestWorkflowInputs:
    def test_set_and_get(self):
        pool = VariablePool()
        pool.set_workflow_inputs({"x": 1, "y": "hello"})
        assert pool.get_workflow_input("x") == 1
        assert pool.get_workflow_input("y") == "hello"

    def test_set_replaces_previous(self):
        pool = VariablePool(workflow_inputs={"a": 1})
        pool.set_workflow_inputs({"b": 2})
        assert pool.get_workflow_input("b") == 2
        with pytest.raises(KeyError):
            pool.get_workflow_input("a")

    def test_missing_key_raises_keyerror(self):
        pool = VariablePool()
        with pytest.raises(KeyError):
            pool.get_workflow_input("nonexistent")

    def test_various_types(self):
        pool = VariablePool(
            workflow_inputs={
                "string": "hello",
                "number": 42,
                "float": 3.14,
                "bool": True,
                "none": None,
                "list": [1, 2, 3],
                "dict": {"nested": True},
            }
        )
        assert pool.get_workflow_input("string") == "hello"
        assert pool.get_workflow_input("number") == 42
        assert pool.get_workflow_input("float") == 3.14
        assert pool.get_workflow_input("bool") is True
        assert pool.get_workflow_input("none") is None
        assert pool.get_workflow_input("list") == [1, 2, 3]
        assert pool.get_workflow_input("dict") == {"nested": True}


# ---------------------------------------------------------------------------
# Node outputs
# ---------------------------------------------------------------------------


class TestNodeOutputs:
    def test_set_and_get_single_output(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"status": 200, "body": {"ok": True}})
        assert pool.get_node_output("fetch", "status") == 200
        assert pool.get_node_output("fetch", "body") == {"ok": True}

    def test_get_full_outputs(self):
        outputs = {"a": 1, "b": 2}
        pool = VariablePool()
        pool.set_node_outputs("node1", outputs)
        assert pool.get_node_outputs("node1") == outputs

    def test_set_replaces_previous_outputs(self):
        pool = VariablePool()
        pool.set_node_outputs("node1", {"v1": True})
        pool.set_node_outputs("node1", {"v2": True})
        assert pool.get_node_outputs("node1") == {"v2": True}
        with pytest.raises(KeyError):
            pool.get_node_output("node1", "v1")

    def test_missing_node_id_raises_keyerror(self):
        pool = VariablePool()
        with pytest.raises(KeyError):
            pool.get_node_output("nonexistent", "key")

    def test_missing_output_key_raises_keyerror(self):
        pool = VariablePool()
        pool.set_node_outputs("node1", {"exists": True})
        with pytest.raises(KeyError):
            pool.get_node_output("node1", "missing")

    def test_missing_node_id_for_full_outputs_raises_keyerror(self):
        pool = VariablePool()
        with pytest.raises(KeyError):
            pool.get_node_outputs("nonexistent")

    def test_multiple_nodes(self):
        pool = VariablePool()
        pool.set_node_outputs("a", {"x": 1})
        pool.set_node_outputs("b", {"y": 2})
        assert pool.get_node_output("a", "x") == 1
        assert pool.get_node_output("b", "y") == 2


# ---------------------------------------------------------------------------
# resolve_reference
# ---------------------------------------------------------------------------


class TestResolveReference:
    def test_workflow_input_ref(self):
        pool = VariablePool(workflow_inputs={"order_id": "abc"})
        assert pool.resolve_reference("{{workflow.input.order_id}}") == "abc"

    def test_node_output_ref(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"status": 200})
        assert pool.resolve_reference("{{nodes.fetch.output.status}}") == 200

    def test_non_reference_returned_as_is(self):
        pool = VariablePool()
        assert pool.resolve_reference("just a string") == "just a string"
        assert pool.resolve_reference("") == ""
        assert pool.resolve_reference("no braces here") == "no braces here"

    def test_partial_braces_returned_as_is(self):
        pool = VariablePool()
        assert pool.resolve_reference("{{incomplete") == "{{incomplete"
        assert pool.resolve_reference("not a {{ref") == "not a {{ref"

    def test_unknown_workflow_input_raises_keyerror(self):
        pool = VariablePool()
        with pytest.raises(KeyError):
            pool.resolve_reference("{{workflow.input.missing}}")

    def test_unknown_node_output_raises_keyerror(self):
        pool = VariablePool()
        with pytest.raises(KeyError):
            pool.resolve_reference("{{nodes.fetch.output.missing}}")

    def test_unknown_node_id_raises_keyerror(self):
        pool = VariablePool()
        with pytest.raises(KeyError):
            pool.resolve_reference("{{nodes.nonexistent.output.key}}")

    def test_workflow_input_with_underscore(self):
        pool = VariablePool(workflow_inputs={"api_token": "secret"})
        assert pool.resolve_reference("{{workflow.input.api_token}}") == "secret"

    def test_node_id_with_underscore(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch_order", {"result": "ok"})
        assert pool.resolve_reference("{{nodes.fetch_order.output.result}}") == "ok"


# ---------------------------------------------------------------------------
# resolve_value
# ---------------------------------------------------------------------------


class TestResolveValue:
    def test_string_with_reference(self):
        pool = VariablePool(workflow_inputs={"x": 42})
        assert pool.resolve_value("{{workflow.input.x}}") == 42

    def test_plain_string_returned_as_is(self):
        pool = VariablePool()
        assert pool.resolve_value("hello world") == "hello world"

    def test_non_string_types_returned_as_is(self):
        pool = VariablePool()
        assert pool.resolve_value(42) == 42
        assert pool.resolve_value(3.14) == 3.14
        assert pool.resolve_value(True) is True
        assert pool.resolve_value(None) is None

    def test_dict_values_resolved_recursively(self):
        pool = VariablePool(workflow_inputs={"name": "Alice"})
        pool.set_node_outputs("greet", {"msg": "hello"})
        result = pool.resolve_value(
            {
                "user": "{{workflow.input.name}}",
                "greeting": "{{nodes.greet.output.msg}}",
                "literal": 42,
            }
        )
        assert result == {
            "user": "Alice",
            "greeting": "hello",
            "literal": 42,
        }

    def test_list_items_resolved_recursively(self):
        pool = VariablePool(workflow_inputs={"a": 1, "b": 2})
        result = pool.resolve_value(
            [
                "{{workflow.input.a}}",
                "{{workflow.input.b}}",
                "literal",
                99,
            ]
        )
        assert result == [1, 2, "literal", 99]

    def test_nested_dict_in_list(self):
        pool = VariablePool(workflow_inputs={"x": "val"})
        result = pool.resolve_value([{"key": "{{workflow.input.x}}"}])
        assert result == [{"key": "val"}]

    def test_nested_list_in_dict(self):
        pool = VariablePool(workflow_inputs={"x": "val"})
        result = pool.resolve_value({"items": ["{{workflow.input.x}}", "static"]})
        assert result == {"items": ["val", "static"]}

    def test_deeply_nested(self):
        pool = VariablePool(workflow_inputs={"v": 1})
        result = pool.resolve_value(
            {
                "level1": {
                    "level2": [
                        {"level3": "{{workflow.input.v}}"},
                    ],
                },
            }
        )
        assert result == {"level1": {"level2": [{"level3": 1}]}}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_empty_pool_round_trip(self):
        pool = VariablePool()
        data = pool.to_dict()
        assert data == {"workflow_inputs": {}, "node_outputs": {}}
        restored = VariablePool.from_dict(data)
        assert restored.to_dict() == data

    def test_full_pool_round_trip(self):
        pool = VariablePool(workflow_inputs={"order_id": "abc", "count": 5})
        pool.set_node_outputs("fetch", {"status": 200, "body": {"ok": True}})
        pool.set_node_outputs("process", {"result": "done"})

        data = pool.to_dict()

        assert data["workflow_inputs"] == {"order_id": "abc", "count": 5}
        assert data["node_outputs"]["fetch"] == {"status": 200, "body": {"ok": True}}
        assert data["node_outputs"]["process"] == {"result": "done"}

        restored = VariablePool.from_dict(data)
        assert restored.get_workflow_input("order_id") == "abc"
        assert restored.get_workflow_input("count") == 5
        assert restored.get_node_output("fetch", "status") == 200
        assert restored.get_node_output("fetch", "body") == {"ok": True}
        assert restored.get_node_output("process", "result") == "done"

    def test_to_dict_returns_new_copy(self):
        pool = VariablePool(workflow_inputs={"k": "v"})
        d1 = pool.to_dict()
        d2 = pool.to_dict()
        assert d1 == d2
        assert d1 is not d2

    def test_from_dict_creates_independent_copy(self):
        data = {"workflow_inputs": {"k": "v"}, "node_outputs": {"n": {"o": 1}}}
        pool = VariablePool.from_dict(data)
        # mutate original data — pool should be unaffected
        data["workflow_inputs"]["k"] = "changed"
        assert pool.get_workflow_input("k") == "v"
