"""Tests for flowkit.nodes.human_input — HumanInputExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.human_input import HumanInputExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


class TestHumanInputExecutor:
    async def test_returns_waiting_status(self):
        pool = VariablePool({"order_id": "42"})
        ctx = NodeContext(
            node_def=NodeDef(
                id="approval",
                type=NodeType.human_input,
                config={
                    "prompt": "Approve order {{workflow.input.order_id}}?",
                    "input_schema": {"approved": {"type": "boolean", "required": True}},
                    "timeout": 3600,
                },
            ),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = HumanInputExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.WAITING
        assert result.outputs == {}
        assert result.error is None

    async def test_no_config(self):
        ctx = NodeContext(
            node_def=NodeDef(id="hi", type=NodeType.human_input),
            variable_pool=VariablePool(),
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = HumanInputExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.WAITING
