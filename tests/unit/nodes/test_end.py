"""Tests for flowkit.nodes.end — EndExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.end import EndExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


class TestEndExecutor:
    async def test_resolves_output_mapping(self):
        pool = VariablePool({"order_id": "123"})
        pool.set_node_outputs("process", {"result": "done", "timestamp": "2026-01-01"})

        ctx = NodeContext(
            node_def=NodeDef(
                id="end",
                type=NodeType.end,
                config={
                    "output_mapping": {
                        "result": "{{nodes.process.output.result}}",
                        "processed_at": "{{nodes.process.output.timestamp}}",
                    }
                },
            ),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = EndExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"result": "done", "processed_at": "2026-01-01"}
        assert result.error is None
        assert result.next_handle == "default"

    async def test_no_config(self):
        pool = VariablePool()
        ctx = NodeContext(
            node_def=NodeDef(id="end", type=NodeType.end),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = EndExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {}

    async def test_empty_output_mapping(self):
        pool = VariablePool()
        ctx = NodeContext(
            node_def=NodeDef(id="end", type=NodeType.end, config={"output_mapping": {}}),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = EndExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {}
