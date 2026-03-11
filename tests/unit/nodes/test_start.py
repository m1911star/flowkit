"""Tests for flowkit.nodes.start — StartExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext, NodeResult
from flowkit.nodes.start import StartExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


class TestStartExecutor:
    async def test_outputs_workflow_inputs(self):
        pool = VariablePool({"order_id": "123", "priority": "high"})
        ctx = NodeContext(
            node_def=NodeDef(id="start", type=NodeType.start),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = StartExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"order_id": "123", "priority": "high"}
        assert result.error is None
        assert result.next_handle == "default"

    async def test_empty_inputs(self):
        pool = VariablePool()
        ctx = NodeContext(
            node_def=NodeDef(id="start", type=NodeType.start),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = StartExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {}
