"""Tests for flowkit.nodes.base — NodeContext, NodeResult, NodeExecutor ABC."""

import uuid

import pytest

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext, NodeExecutor, NodeResult
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


class TestNodeContext:
    def test_construction(self):
        node_def = NodeDef(id="n1", type=NodeType.start)
        pool = VariablePool({"x": 1})
        run_id = uuid.uuid4()
        node_run_id = uuid.uuid4()

        ctx = NodeContext(
            node_def=node_def,
            variable_pool=pool,
            run_id=run_id,
            node_run_id=node_run_id,
        )

        assert ctx.node_def is node_def
        assert ctx.variable_pool is pool
        assert ctx.run_id == run_id
        assert ctx.node_run_id == node_run_id


class TestNodeResult:
    def test_defaults(self):
        result = NodeResult(status=NodeState.COMPLETED, outputs={"key": "val"})

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"key": "val"}
        assert result.error is None
        assert result.next_handle == "default"

    def test_failed_with_error(self):
        result = NodeResult(
            status=NodeState.FAILED,
            outputs={},
            error="something broke",
            next_handle="default",
        )

        assert result.status == NodeState.FAILED
        assert result.error == "something broke"

    def test_waiting_status(self):
        result = NodeResult(status=NodeState.WAITING, outputs={})

        assert result.status == NodeState.WAITING

    def test_custom_handle(self):
        result = NodeResult(
            status=NodeState.COMPLETED,
            outputs={},
            next_handle="is_high",
        )

        assert result.next_handle == "is_high"


class TestNodeExecutor:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            NodeExecutor()  # type: ignore[abstract]

    async def test_subclass_can_execute(self):
        class DummyExecutor(NodeExecutor):
            async def execute(self, ctx: NodeContext) -> NodeResult:
                return NodeResult(status=NodeState.COMPLETED, outputs={"ok": True})

        executor = DummyExecutor()
        node_def = NodeDef(id="n1", type=NodeType.start)
        pool = VariablePool()
        ctx = NodeContext(
            node_def=node_def,
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        result = await executor.execute(ctx)
        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"ok": True}
