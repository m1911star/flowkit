"""Tests for WorkflowExecutor — orchestrates the full workflow run lifecycle."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from flowkit.definition.schema import (
    EdgeDef,
    NodeDef,
    NodeType,
    WorkflowDefinition,
    WorkflowMetadata,
)
from flowkit.engine.executor import WorkflowExecutor
from flowkit.runtime.state import RunState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_definition(
    nodes: list[NodeDef],
    edges: list[EdgeDef],
    inputs: dict | None = None,
    outputs: dict | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        version="1.0",
        metadata=WorkflowMetadata(name="test-wf"),
        nodes=nodes,
        edges=edges,
        inputs=inputs or {},
        outputs=outputs or {},
    )


# ---------------------------------------------------------------------------
# Linear workflow: start -> code -> end
# ---------------------------------------------------------------------------


def _linear_workflow() -> WorkflowDefinition:
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="add",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"sum": a + b}',
                    "inputs": {
                        "a": "{{workflow.input.a}}",
                        "b": "{{workflow.input.b}}",
                    },
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={
                    "output_mapping": {
                        "total": "{{nodes.add.output.sum}}",
                    },
                },
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="add"),
            EdgeDef(id="e2", source="add", target="end"),
        ],
    )


class TestWorkflowExecutorLinear:
    """Execute a simple linear workflow end-to-end."""

    async def test_linear_workflow_completes(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _linear_workflow(),
            inputs={"a": 3, "b": 7},
        )
        assert result.status == RunState.COMPLETED

    async def test_linear_workflow_returns_outputs(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _linear_workflow(),
            inputs={"a": 3, "b": 7},
        )
        assert result.outputs["total"] == 10

    async def test_linear_workflow_records_events(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _linear_workflow(),
            inputs={"a": 1, "b": 2},
        )
        events = result.events
        node_ids = [e["node_id"] for e in events if e["type"] == "node_completed"]
        assert "start" in node_ids
        assert "add" in node_ids
        assert "end" in node_ids


# ---------------------------------------------------------------------------
# Branching workflow: start -> if_else --(cond_1)-> code_true -> end
#                                       \-(else)-> code_false -> end
# ---------------------------------------------------------------------------


def _branching_workflow() -> WorkflowDefinition:
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="branch",
                type=NodeType.if_else,
                config={
                    "conditions": [
                        {"id": "cond_1", "expression": "{{workflow.input.x}} > 10"},
                    ],
                },
            ),
            NodeDef(
                id="code_true",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"label": "big"}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="code_false",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"label": "small"}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={
                    "output_mapping": {},
                },
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="branch"),
            EdgeDef(id="e2", source="branch", target="code_true", source_handle="cond_1"),
            EdgeDef(id="e3", source="branch", target="code_false", source_handle="else"),
            EdgeDef(id="e4", source="code_true", target="end"),
            EdgeDef(id="e5", source="code_false", target="end"),
        ],
    )


class TestWorkflowExecutorBranching:
    """Execute branching workflows — only the selected branch runs."""

    async def test_branch_true_path(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _branching_workflow(),
            inputs={"x": 20},
        )
        assert result.status == RunState.COMPLETED
        events = result.events
        completed_ids = {e["node_id"] for e in events if e["type"] == "node_completed"}
        assert "code_true" in completed_ids
        assert "code_false" not in completed_ids

    async def test_branch_false_path(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _branching_workflow(),
            inputs={"x": 5},
        )
        assert result.status == RunState.COMPLETED
        events = result.events
        completed_ids = {e["node_id"] for e in events if e["type"] == "node_completed"}
        assert "code_false" in completed_ids
        assert "code_true" not in completed_ids


# ---------------------------------------------------------------------------
# Human input (pause) workflow: start -> human -> end
# ---------------------------------------------------------------------------


def _human_input_workflow() -> WorkflowDefinition:
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="human",
                type=NodeType.human_input,
                config={
                    "prompt": "Enter your name",
                    "input_schema": {"name": {"type": "string"}},
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={"output_mapping": {}},
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="human"),
            EdgeDef(id="e2", source="human", target="end"),
        ],
    )


class TestWorkflowExecutorPause:
    """Workflow should pause when hitting a human_input node."""

    async def test_pauses_at_human_input(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _human_input_workflow(),
            inputs={},
        )
        assert result.status == RunState.PAUSED
        assert result.waiting_node == "human"

    async def test_paused_workflow_events(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _human_input_workflow(),
            inputs={},
        )
        events = result.events
        completed_ids = {e["node_id"] for e in events if e["type"] == "node_completed"}
        assert "start" in completed_ids
        waiting_ids = {e["node_id"] for e in events if e["type"] == "node_waiting"}
        assert "human" in waiting_ids


# ---------------------------------------------------------------------------
# Error handling: start -> bad_code -> end
# ---------------------------------------------------------------------------


def _failing_workflow() -> WorkflowDefinition:
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="bad_code",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": "raise ValueError('intentional')",
                    "inputs": {},
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={"output_mapping": {}},
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="bad_code"),
            EdgeDef(id="e2", source="bad_code", target="end"),
        ],
    )


class TestWorkflowExecutorErrors:
    """Workflow fails if a node fails."""

    async def test_workflow_fails_on_node_error(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _failing_workflow(),
            inputs={},
        )
        assert result.status == RunState.FAILED
        assert result.error is not None

    async def test_failed_workflow_captures_error_info(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _failing_workflow(),
            inputs={},
        )
        assert "bad_code" in result.error


# ---------------------------------------------------------------------------
# HTTP workflow with mock: start -> http -> end
# ---------------------------------------------------------------------------


def _http_workflow() -> WorkflowDefinition:
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="fetch",
                type=NodeType.http,
                config={
                    "method": "GET",
                    "url": "https://api.example.com/data",
                    "timeout": 5,
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={
                    "output_mapping": {
                        "status": "{{nodes.fetch.output.status_code}}",
                    },
                },
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="fetch"),
            EdgeDef(id="e2", source="fetch", target="end"),
        ],
    )


class TestWorkflowExecutorHttp:
    """HTTP node execution with mocked httpx."""

    async def test_http_workflow_completes(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": "hello"}
        mock_response.content = b'{"data": "hello"}'
        mock_response.text = '{"data": "hello"}'

        mock_client_instance = AsyncMock()
        mock_client_instance.request.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("flowkit.nodes.http.httpx.AsyncClient", return_value=mock_client_instance):
            executor = WorkflowExecutor()
            result = await executor.execute_workflow(
                _http_workflow(),
                inputs={},
            )
            assert result.status == RunState.COMPLETED
            assert result.outputs["status"] == 200


# ---------------------------------------------------------------------------
# Parallel execution: start -> fork -> [code_a, code_b] -> end
# ---------------------------------------------------------------------------


def _parallel_diamond_workflow() -> WorkflowDefinition:
    """Diamond: start → fork → [code_a, code_b] → end."""
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="fork",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"forked": True}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="code_a",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"a": 1}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="code_b",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"b": 2}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={
                    "output_mapping": {
                        "a": "{{nodes.code_a.output.a}}",
                        "b": "{{nodes.code_b.output.b}}",
                    },
                },
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="fork"),
            EdgeDef(id="e2", source="fork", target="code_a"),
            EdgeDef(id="e3", source="fork", target="code_b"),
            EdgeDef(id="e4", source="code_a", target="end"),
            EdgeDef(id="e5", source="code_b", target="end"),
        ],
    )


def _parallel_diamond_with_failure() -> WorkflowDefinition:
    """Diamond where code_b raises an error."""
    return _make_definition(
        nodes=[
            NodeDef(id="start", type=NodeType.start),
            NodeDef(
                id="fork",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"forked": True}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="code_a",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": 'result = {"a": 1}',
                    "inputs": {},
                },
            ),
            NodeDef(
                id="code_b",
                type=NodeType.code,
                config={
                    "language": "python",
                    "source": "raise ValueError('boom')",
                    "inputs": {},
                },
            ),
            NodeDef(
                id="end",
                type=NodeType.end,
                config={"output_mapping": {}},
            ),
        ],
        edges=[
            EdgeDef(id="e1", source="start", target="fork"),
            EdgeDef(id="e2", source="fork", target="code_a"),
            EdgeDef(id="e3", source="fork", target="code_b"),
            EdgeDef(id="e4", source="code_a", target="end"),
            EdgeDef(id="e5", source="code_b", target="end"),
        ],
    )


class TestWorkflowExecutorParallel:
    """Parallel branches execute concurrently via asyncio.gather."""

    async def test_parallel_branches_both_execute(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _parallel_diamond_workflow(),
            inputs={},
        )

        assert result.status == RunState.COMPLETED
        assert result.outputs["a"] == 1
        assert result.outputs["b"] == 2

    async def test_parallel_branch_failure_fails_workflow(self) -> None:
        executor = WorkflowExecutor()
        result = await executor.execute_workflow(
            _parallel_diamond_with_failure(),
            inputs={},
        )

        assert result.status == RunState.FAILED
        assert result.error is not None
        assert "code_b" in result.error
