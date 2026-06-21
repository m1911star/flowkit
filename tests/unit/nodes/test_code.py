"""Tests for flowkit.nodes.code — CodeExecutor."""
import uuid
from unittest.mock import MagicMock, patch

from flowkit.definition.schema import NodeDef, NodeType
from flowkit.nodes.base import NodeContext
from flowkit.nodes.code import CodeExecutor
from flowkit.runtime.state import NodeState
from flowkit.runtime.variable_pool import VariablePool


def _make_ctx(
    source: str, inputs: dict | None = None, pool: VariablePool | None = None
) -> NodeContext:
    config = {
        "language": "python",
        "source": source,
        "inputs": inputs or {},
    }
    return NodeContext(
        node_def=NodeDef(id="code_node", type=NodeType.code, config=config),
        variable_pool=pool or VariablePool(),
        run_id=uuid.uuid4(),
        node_run_id=uuid.uuid4(),
    )


class TestCodeExecutor:
    async def test_simple_computation(self):
        ctx = _make_ctx(
            source='result = {"sum": a + b}',
            inputs={"a": "{{workflow.input.a}}", "b": "{{workflow.input.b}}"},
            pool=VariablePool({"a": 3, "b": 5}),
        )

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"sum": 8}

    async def test_no_result_variable(self):
        ctx = _make_ctx(source="x = 42")

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {}

    async def test_error_handling(self):
        ctx = _make_ctx(source='raise ValueError("bad")')

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "bad" in result.error

    async def test_restricted_builtins_no_import(self):
        ctx = _make_ctx(source="import os")

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED

    async def test_restricted_builtins_no_open(self):
        ctx = _make_ctx(source='f = open("/etc/passwd")')

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED

    async def test_string_manipulation(self):
        ctx = _make_ctx(
            source='result = {"greeting": f"Hello, {name}!"}',
            inputs={"name": "{{workflow.input.name}}"},
            pool=VariablePool({"name": "World"}),
        )

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"greeting": "Hello, World!"}

    async def test_list_processing(self):
        ctx = _make_ctx(
            source='result = {"total": sum(items), "count": len(items)}',
            inputs={"items": "{{workflow.input.items}}"},
            pool=VariablePool({"items": [1, 2, 3, 4, 5]}),
        )

        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.COMPLETED
        assert result.outputs == {"total": 15, "count": 5}


class TestCodeSandboxHardening:
    """Tests for AST pre-validation, timeout, and size limits."""

    async def test_rejects_import_statement(self):
        ctx = _make_ctx(source="import os")
        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Forbidden: import statement" in result.error

    async def test_rejects_import_from(self):
        ctx = _make_ctx(source="from os import path")
        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Forbidden: from-import statement" in result.error

    async def test_rejects_dunder_access(self):
        ctx = _make_ctx(source="x = ().__class__.__subclasses__()")
        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Forbidden: access to private/dunder attribute" in result.error

    async def test_rejects_eval_call(self):
        ctx = _make_ctx(source="eval('1+1')")
        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Forbidden: call to 'eval'" in result.error

    async def test_rejects_exec_call(self):
        ctx = _make_ctx(source="exec('x=1')")
        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Forbidden: call to 'exec'" in result.error

    async def test_timeout_kills_execution(self):
        # Simulate timeout by mocking thread.join to not finish and is_alive to return True
        ctx = _make_ctx(source="result = {'x': 1}")
        executor = CodeExecutor()

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True  # Simulate never-finishing thread

        with (
            patch("flowkit.nodes.code.threading.Thread", return_value=mock_thread),
            patch("flowkit.nodes.code._DEFAULT_TIMEOUT", 0.1),
        ):
            result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "timed out" in result.error
        mock_thread.start.assert_called_once()
        mock_thread.join.assert_called_once()

    async def test_rejects_oversized_source(self):
        source = "x = 1\n" * 10_000  # Well over 50_000 chars
        ctx = _make_ctx(source=source)
        executor = CodeExecutor()
        result = await executor.execute(ctx)

        assert result.status == NodeState.FAILED
        assert "Source too large" in result.error
