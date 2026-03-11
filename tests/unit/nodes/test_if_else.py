"""Tests for flowkit.nodes.if_else — IfElseExecutor."""

import uuid

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.if_else import IfElseExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


def _make_ctx(conditions: list[dict], pool: VariablePool | None = None) -> NodeContext:
    return NodeContext(
        node_def=NodeDef(
            id="branch",
            type=NodeType.if_else,
            config={"conditions": conditions},
        ),
        variable_pool=pool or VariablePool(),
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


class TestIfElseExecutor:
    async def test_first_condition_matches(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"priority": "high"})

        ctx = _make_ctx(
            conditions=[
                {"id": "is_high", "expression": "{{nodes.fetch.output.priority}} == 'high'"},
                {"id": "is_low", "expression": "{{nodes.fetch.output.priority}} == 'low'"},
            ],
            pool=pool,
        )

        executor = IfElseExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "is_high"

    async def test_second_condition_matches(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"priority": "low"})

        ctx = _make_ctx(
            conditions=[
                {"id": "is_high", "expression": "{{nodes.fetch.output.priority}} == 'high'"},
                {"id": "is_low", "expression": "{{nodes.fetch.output.priority}} == 'low'"},
            ],
            pool=pool,
        )

        executor = IfElseExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "is_low"

    async def test_else_when_no_match(self):
        pool = VariablePool()
        pool.set_node_outputs("fetch", {"priority": "medium"})

        ctx = _make_ctx(
            conditions=[
                {"id": "is_high", "expression": "{{nodes.fetch.output.priority}} == 'high'"},
                {"id": "is_low", "expression": "{{nodes.fetch.output.priority}} == 'low'"},
            ],
            pool=pool,
        )

        executor = IfElseExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.next_handle == "else"

    async def test_equality_operator(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 42})

        ctx = _make_ctx(
            conditions=[{"id": "match", "expression": "{{nodes.n1.output.val}} == 42"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "match"

    async def test_not_equal_operator(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 10})

        ctx = _make_ctx(
            conditions=[{"id": "diff", "expression": "{{nodes.n1.output.val}} != 20"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "diff"

    async def test_greater_than(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 100})

        ctx = _make_ctx(
            conditions=[{"id": "big", "expression": "{{nodes.n1.output.val}} > 50"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "big"

    async def test_less_than(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 5})

        ctx = _make_ctx(
            conditions=[{"id": "small", "expression": "{{nodes.n1.output.val}} < 10"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "small"

    async def test_greater_equal(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 50})

        ctx = _make_ctx(
            conditions=[{"id": "gte", "expression": "{{nodes.n1.output.val}} >= 50"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "gte"

    async def test_less_equal(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 50})

        ctx = _make_ctx(
            conditions=[{"id": "lte", "expression": "{{nodes.n1.output.val}} <= 50"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "lte"

    async def test_in_operator(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"status": "active"})

        ctx = _make_ctx(
            conditions=[
                {"id": "valid", "expression": "{{nodes.n1.output.status}} in ['active', 'pending']"}
            ],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "valid"

    async def test_not_in_operator(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"status": "deleted"})

        ctx = _make_ctx(
            conditions=[
                {
                    "id": "invalid",
                    "expression": "{{nodes.n1.output.status}} not in ['active', 'pending']",
                }
            ],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "invalid"

    async def test_greater_than_not_matching(self):
        pool = VariablePool()
        pool.set_node_outputs("n1", {"val": 3})

        ctx = _make_ctx(
            conditions=[{"id": "big", "expression": "{{nodes.n1.output.val}} > 50"}],
            pool=pool,
        )

        result = await IfElseExecutor().execute(ctx)
        assert result.next_handle == "else"
