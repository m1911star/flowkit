"""Tests for flowkit.nodes.loop — LoopExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.loop import LoopExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


def _make_ctx(items_ref: str, pool: VariablePool, **config_overrides) -> NodeContext:
    config = {
        "items": items_ref,
        "item_variable": config_overrides.get("item_variable", "item"),
        "index_variable": config_overrides.get("index_variable", "index"),
        "max_iterations": config_overrides.get("max_iterations", 100),
    }
    return NodeContext(
        node_def=NodeDef(id="loop_node", type=NodeType.loop, config=config),
        variable_pool=pool,
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


class TestLoopExecutor:
    async def test_has_items_returns_body(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"orders": [1, 2, 3]})

        ctx = _make_ctx("{{nodes.fetch.output.orders}}", pool)

        executor = LoopExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "body"
        assert result.outputs["count"] == 3

    async def test_empty_items_returns_completed(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"orders": []})

        ctx = _make_ctx("{{nodes.fetch.output.orders}}", pool)

        executor = LoopExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "completed"
        assert result.outputs["count"] == 0
        assert result.outputs["results"] == []

    async def test_sets_item_and_index_variables(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"items": ["a", "b", "c"]})

        ctx = _make_ctx(
            "{{nodes.fetch.output.items}}",
            pool,
            item_variable="current",
            index_variable="idx",
        )

        executor = LoopExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "body"
        # First item and index should be set in the pool
        node_outputs = pool.get_node_outputs("loop_node")
        assert node_outputs["current"] == "a"
        assert node_outputs["idx"] == 0

    async def test_non_list_items_fails(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"data": "not_a_list"})

        ctx = _make_ctx("{{nodes.fetch.output.data}}", pool)

        executor = LoopExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error is not None
