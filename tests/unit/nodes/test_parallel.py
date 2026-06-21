"""Tests for flowkit.nodes.parallel — ParallelExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.parallel import ParallelExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


def _make_ctx(
    items_ref: str, pool: VariablePool, *, config: dict | None = None, **config_overrides
) -> NodeContext:
    cfg = config if config is not None else {
        "items": items_ref,
        "item_variable": config_overrides.get("item_variable", "item"),
        "index_variable": config_overrides.get("index_variable", "index"),
        "max_concurrency": config_overrides.get("max_concurrency", 10),
    }
    return NodeContext(
        node_def=NodeDef(id="parallel_node", type=NodeType.parallel, config=cfg),
        variable_pool=pool,
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


class TestParallelExecutor:
    async def test_resolves_items_and_outputs(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"orders": [1, 2, 3]})

        ctx = _make_ctx("{{nodes.fetch.output.orders}}", pool)

        executor = ParallelExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "body"
        assert result.outputs["count"] == 3

    async def test_empty_items_returns_completed(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"orders": []})

        ctx = _make_ctx("{{nodes.fetch.output.orders}}", pool)

        executor = ParallelExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "completed"
        assert result.outputs["count"] == 0
        assert result.outputs["results"] == []

    async def test_non_list_fails(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"data": "not_a_list"})

        ctx = _make_ctx("{{nodes.fetch.output.data}}", pool)

        executor = ParallelExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error is not None
        assert "str" in result.error

    async def test_stores_first_item_in_pool(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"items": ["a", "b", "c"]})

        ctx = _make_ctx("{{nodes.fetch.output.items}}", pool)

        executor = ParallelExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "body"

        node_outputs = pool.get_node_outputs("parallel_node")
        assert node_outputs["item"] == "a"
        assert node_outputs["index"] == 0
        assert node_outputs["_items"] == ["a", "b", "c"]
        assert node_outputs["_total"] == 3

    async def test_invalid_config(self):
        pool = VariablePool()
        ctx = NodeContext(
            node_def=NodeDef(id="parallel_node", type=NodeType.parallel, config=None),
            variable_pool=pool,
            run_id=uuid.uuid4(),
            node_run_id=uuid.uuid4(),
        )

        executor = ParallelExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert result.error is not None
        assert "config" in result.error.lower()
