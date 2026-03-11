"""Tests for flowkit.definition.schema — Pydantic v2 DSL models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from flowkit.definition.schema import (
    BackoffStrategy,
    CodeNodeConfig,
    Condition,
    DataType,
    EdgeDef,
    EndNodeConfig,
    HttpMethod,
    HttpNodeConfig,
    HumanInputConfig,
    IfElseConfig,
    InputDef,
    LoopConfig,
    NodeDef,
    NodeType,
    OutputDef,
    Position,
    RetryConfig,
    WorkflowDefinition,
    WorkflowMetadata,
)

# ---------------------------------------------------------------------------
# Helpers — reusable minimal valid workflow
# ---------------------------------------------------------------------------


def _minimal_workflow(**overrides: object) -> dict:
    """Return a dict that deserializes to a minimal valid WorkflowDefinition."""
    base: dict = {
        "version": "1.0",
        "metadata": {"name": "test-workflow"},
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "end"},
        ],
    }
    base.update(overrides)
    return base


# ===========================================================================
# Enum Tests
# ===========================================================================


class TestDataType:
    def test_all_values(self):
        assert set(DataType) == {
            DataType.string,
            DataType.number,
            DataType.boolean,
            DataType.object,
            DataType.array,
            DataType.any,
        }

    def test_string_value(self):
        assert DataType("string") is DataType.string


class TestNodeType:
    def test_all_values(self):
        assert set(NodeType) == {
            NodeType.start,
            NodeType.end,
            NodeType.http,
            NodeType.code,
            NodeType.if_else,
            NodeType.loop,
            NodeType.human_input,
        }


class TestHttpMethod:
    def test_all_methods(self):
        assert set(HttpMethod) == {
            HttpMethod.GET,
            HttpMethod.POST,
            HttpMethod.PUT,
            HttpMethod.PATCH,
            HttpMethod.DELETE,
        }


# ===========================================================================
# InputDef / OutputDef
# ===========================================================================


class TestInputDef:
    def test_minimal(self):
        inp = InputDef(type=DataType.string)
        assert inp.type == DataType.string
        assert inp.required is False
        assert inp.default is None

    def test_full(self):
        inp = InputDef(
            type=DataType.string,
            required=True,
            default="hello",
            enum=["hello", "world"],
            description="A greeting",
        )
        assert inp.required is True
        assert inp.default == "hello"
        assert inp.enum == ["hello", "world"]

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            InputDef(type=DataType.string, bogus="x")  # type: ignore[call-arg]


class TestOutputDef:
    def test_minimal(self):
        out = OutputDef(type=DataType.boolean)
        assert out.value is None

    def test_with_value(self):
        out = OutputDef(type=DataType.string, value="{{nodes.x.output.y}}")
        assert out.value == "{{nodes.x.output.y}}"


# ===========================================================================
# Node Config Models
# ===========================================================================


class TestRetryConfig:
    def test_defaults(self):
        rc = RetryConfig()
        assert rc.max_attempts == 1
        assert rc.backoff == BackoffStrategy.fixed

    def test_exponential(self):
        rc = RetryConfig(max_attempts=3, backoff=BackoffStrategy.exponential)
        assert rc.max_attempts == 3


class TestHttpNodeConfig:
    def test_minimal(self):
        cfg = HttpNodeConfig(method=HttpMethod.GET, url="https://example.com")
        assert cfg.timeout == 30
        assert cfg.headers == {}

    def test_full(self):
        cfg = HttpNodeConfig(
            method=HttpMethod.POST,
            url="https://api.example.com/orders",
            headers={"Content-Type": "application/json"},
            body='{"key": "value"}',
            timeout=60,
            retry=RetryConfig(max_attempts=3, backoff=BackoffStrategy.exponential),
        )
        assert cfg.retry is not None
        assert cfg.retry.max_attempts == 3

    def test_rejects_invalid_method(self):
        with pytest.raises(ValidationError):
            HttpNodeConfig(method="INVALID", url="https://x.com")  # type: ignore[arg-type]


class TestCodeNodeConfig:
    def test_minimal(self):
        cfg = CodeNodeConfig(language="python", source="return {'x': 1}")
        assert cfg.inputs == {}

    def test_with_inputs(self):
        cfg = CodeNodeConfig(
            language="python",
            source="return {'doubled': inputs['v'] * 2}",
            inputs={"v": "{{nodes.a.output.val}}"},
        )
        assert cfg.inputs["v"] == "{{nodes.a.output.val}}"


class TestIfElseConfig:
    def test_single_condition(self):
        cfg = IfElseConfig(conditions=[Condition(id="is_high", expression="x == 'high'")])
        assert len(cfg.conditions) == 1

    def test_multiple_conditions(self):
        cfg = IfElseConfig(
            conditions=[
                Condition(id="c1", expression="x > 10"),
                Condition(id="c2", expression="x > 5"),
            ]
        )
        assert len(cfg.conditions) == 2


class TestLoopConfig:
    def test_defaults(self):
        cfg = LoopConfig(items="{{nodes.x.output.list}}")
        assert cfg.item_variable == "item"
        assert cfg.index_variable == "index"
        assert cfg.max_iterations == 100

    def test_custom(self):
        cfg = LoopConfig(
            items="{{nodes.x.output.list}}",
            item_variable="order",
            index_variable="i",
            max_iterations=50,
        )
        assert cfg.item_variable == "order"


class TestHumanInputConfig:
    def test_minimal(self):
        cfg = HumanInputConfig(prompt="Please approve")
        assert cfg.timeout == 86400
        assert cfg.input_schema == {}

    def test_full(self):
        cfg = HumanInputConfig(
            prompt="Approve?",
            input_schema={"approved": {"type": "boolean", "required": True}},
            timeout=3600,
        )
        assert cfg.timeout == 3600


class TestEndNodeConfig:
    def test_defaults(self):
        cfg = EndNodeConfig()
        assert cfg.output_mapping == {}

    def test_with_mapping(self):
        cfg = EndNodeConfig(
            output_mapping={
                "result": "{{nodes.process.output.result}}",
            }
        )
        assert "result" in cfg.output_mapping


# ===========================================================================
# NodeDef
# ===========================================================================


class TestNodeDef:
    def test_minimal(self):
        node = NodeDef(id="start", type=NodeType.start)
        assert node.label is None
        assert node.config is None

    def test_with_position(self):
        node = NodeDef(
            id="fetch",
            type=NodeType.http,
            position=Position(x=100, y=200),
        )
        assert node.position is not None
        assert node.position.x == 100

    def test_invalid_id_uppercase(self):
        with pytest.raises(ValidationError, match="a-z0-9_"):
            NodeDef(id="FetchOrder", type=NodeType.http)

    def test_invalid_id_dash(self):
        with pytest.raises(ValidationError, match="a-z0-9_"):
            NodeDef(id="fetch-order", type=NodeType.http)

    def test_invalid_id_spaces(self):
        with pytest.raises(ValidationError, match="a-z0-9_"):
            NodeDef(id="fetch order", type=NodeType.http)

    def test_parsed_config_http(self):
        node = NodeDef(
            id="fetch",
            type=NodeType.http,
            config={"method": "GET", "url": "https://x.com"},
        )
        cfg = node.parsed_config()
        assert isinstance(cfg, HttpNodeConfig)

    def test_parsed_config_none_for_start(self):
        node = NodeDef(id="start", type=NodeType.start)
        assert node.parsed_config() is None

    def test_parsed_config_end(self):
        node = NodeDef(
            id="end",
            type=NodeType.end,
            config={"output_mapping": {"k": "v"}},
        )
        cfg = node.parsed_config()
        assert isinstance(cfg, EndNodeConfig)


# ===========================================================================
# EdgeDef
# ===========================================================================


class TestEdgeDef:
    def test_defaults(self):
        edge = EdgeDef(id="e1", source="a", target="b")
        assert edge.source_handle == "default"
        assert edge.target_handle == "default"

    def test_custom_handles(self):
        edge = EdgeDef(
            id="e2",
            source="if_node",
            target="branch_a",
            source_handle="is_high",
        )
        assert edge.source_handle == "is_high"


# ===========================================================================
# WorkflowMetadata
# ===========================================================================


class TestWorkflowMetadata:
    def test_valid_name(self):
        m = WorkflowMetadata(name="order-processing")
        assert m.name == "order-processing"

    def test_invalid_name_uppercase(self):
        with pytest.raises(ValidationError, match="a-z0-9"):
            WorkflowMetadata(name="OrderProcessing")

    def test_invalid_name_underscore(self):
        with pytest.raises(ValidationError, match="a-z0-9"):
            WorkflowMetadata(name="order_processing")


# ===========================================================================
# WorkflowDefinition
# ===========================================================================


class TestWorkflowDefinition:
    def test_minimal_valid(self):
        wf = WorkflowDefinition(**_minimal_workflow())
        assert wf.version == "1.0"
        assert wf.metadata.name == "test-workflow"
        assert len(wf.nodes) == 2
        assert len(wf.edges) == 1

    def test_invalid_version(self):
        with pytest.raises(ValidationError, match="version"):
            WorkflowDefinition(**_minimal_workflow(version="2.0"))

    def test_inputs_and_outputs(self):
        wf = WorkflowDefinition(
            **_minimal_workflow(
                inputs={
                    "order_id": {"type": "string", "required": True},
                },
                outputs={
                    "result": {"type": "string"},
                },
            )
        )
        assert "order_id" in wf.inputs
        assert wf.inputs["order_id"].required is True
        assert "result" in wf.outputs

    def test_serialization_roundtrip(self):
        data = _minimal_workflow()
        wf = WorkflowDefinition(**data)
        dumped = wf.model_dump(mode="python")
        wf2 = WorkflowDefinition(**dumped)
        assert wf == wf2

    def test_json_roundtrip(self):
        wf = WorkflowDefinition(**_minimal_workflow())
        json_str = wf.model_dump_json()
        wf2 = WorkflowDefinition.model_validate_json(json_str)
        assert wf == wf2

    def test_rejects_extra_top_level_fields(self):
        data = _minimal_workflow()
        data["extra_field"] = "nope"
        with pytest.raises(ValidationError):
            WorkflowDefinition(**data)


# ===========================================================================
# Full Example from Spec
# ===========================================================================


class TestSpecExample:
    """Test the complete order-approval example from the DSL v1 spec."""

    def test_order_approval_workflow_parses(self):
        data = {
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
        wf = WorkflowDefinition(**data)
        assert wf.metadata.name == "order-approval"
        assert len(wf.nodes) == 6
        assert len(wf.edges) == 6

        # Verify parsed configs
        http_node = next(n for n in wf.nodes if n.type == NodeType.http)
        http_cfg = http_node.parsed_config()
        assert isinstance(http_cfg, HttpNodeConfig)
        assert http_cfg.method == HttpMethod.GET

        if_else_node = next(n for n in wf.nodes if n.type == NodeType.if_else)
        if_cfg = if_else_node.parsed_config()
        assert isinstance(if_cfg, IfElseConfig)
        assert len(if_cfg.conditions) == 1

        code_node = next(n for n in wf.nodes if n.type == NodeType.code)
        code_cfg = code_node.parsed_config()
        assert isinstance(code_cfg, CodeNodeConfig)
        assert code_cfg.language == "python"
