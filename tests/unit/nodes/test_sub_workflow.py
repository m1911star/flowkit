"""Tests for flowkit.nodes.sub_workflow — SubWorkflowExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.sub_workflow import SubWorkflowExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


def _make_ctx(
    definition: dict,
    input_mapping: dict | None = None,
    pool: VariablePool | None = None,
) -> NodeContext:
    config: dict = {"definition": definition}
    if input_mapping:
        config["input_mapping"] = input_mapping
    node_def = NodeDef(id="sub_wf", type=NodeType.sub_workflow, config=config)
    return NodeContext(
        node_def=node_def,
        variable_pool=pool or VariablePool(),
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


_CHILD_DEF = {
    "version": "1.0",
    "metadata": {"name": "child-wf"},
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "end"},
    ],
}

_CHILD_WITH_CODE = {
    "version": "1.0",
    "metadata": {"name": "child-code"},
    "inputs": {"x": {"type": "number"}},
    "nodes": [
        {"id": "start", "type": "start"},
        {
            "id": "compute",
            "type": "code",
            "config": {
                "language": "python",
                "source": "result = {'doubled': x * 2}",
                "inputs": {"x": "{{workflow.input.x}}"},
            },
        },
        {
            "id": "end",
            "type": "end",
            "config": {"output_mapping": {"doubled": "{{nodes.compute.output.doubled}}"}},
        },
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "compute"},
        {"id": "e2", "source": "compute", "target": "end"},
    ],
}

_CHILD_WITH_HUMAN_INPUT = {
    "version": "1.0",
    "metadata": {"name": "child-human"},
    "nodes": [
        {"id": "start", "type": "start"},
        {
            "id": "approval",
            "type": "human_input",
            "config": {"prompt": "Approve?"},
        },
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "approval"},
        {"id": "e2", "source": "approval", "target": "end"},
    ],
}

_CHILD_WITH_ERROR = {
    "version": "1.0",
    "metadata": {"name": "child-error"},
    "nodes": [
        {"id": "start", "type": "start"},
        {
            "id": "bad_code",
            "type": "code",
            "config": {
                "language": "python",
                "source": 'raise ValueError("intentional failure")',
            },
        },
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "bad_code"},
        {"id": "e2", "source": "bad_code", "target": "end"},
    ],
}


class TestSubWorkflowExecutor:
    async def test_simple_child_workflow_completes(self):
        ctx = _make_ctx(definition=_CHILD_DEF)
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {}
        assert result.error is None

    async def test_child_with_code_returns_outputs(self):
        ctx = _make_ctx(
            definition=_CHILD_WITH_CODE,
            input_mapping={"x": "{{workflow.input.x}}"},
            pool=VariablePool({"x": 5}),
        )
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"doubled": 10}

    async def test_child_with_input_mapping(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch_order", {"order_id": "ORD-123"})
        ctx = _make_ctx(
            definition=_CHILD_DEF,
            input_mapping={"order_id": "{{nodes.fetch_order.output.order_id}}"},
            pool=pool,
        )
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED

    async def test_invalid_child_definition_fails(self):
        ctx = _make_ctx(definition={"invalid": True})
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error is not None
        assert "Invalid child workflow definition" in result.error

    async def test_child_workflow_failure_propagates(self):
        ctx = _make_ctx(definition=_CHILD_WITH_ERROR)
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error is not None
        assert "Sub-workflow failed" in result.error

    async def test_child_workflow_pause_becomes_waiting(self):
        ctx = _make_ctx(definition=_CHILD_WITH_HUMAN_INPUT)
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.WAITING
        assert result.error is None

    async def test_no_config_fails(self):
        node_def = NodeDef(id="sub_wf", type=NodeType.sub_workflow, config=None)
        ctx = NodeContext(
            node_def=node_def,
            variable_pool=VariablePool(),
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )
        executor = SubWorkflowExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error is not None
        assert "Invalid or missing" in result.error
