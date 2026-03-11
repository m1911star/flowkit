"""Integration tests — if/else branching workflow execution."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from tests.integration.conftest import (
    ExecutionResult,
    Repos,
    create_workflow_and_version,
    execute_workflow,
)


# --------------------------------------------------------------------------- #
# DSL definitions
# --------------------------------------------------------------------------- #


def _if_else_definition() -> dict[str, Any]:
    """start → if_else → [true_branch: code_a, else: code_b] → end.

    Condition: ``value > 10``.
    - true branch (code_a): outputs ``{"result": value * 2}``
    - else branch (code_b): outputs ``{"result": value + 100}``
    """
    return {
        "version": "1.0",
        "metadata": {"name": "branching-simple", "description": "if/else branch test"},
        "inputs": {
            "value": {"type": "number", "required": True},
        },
        "outputs": {},
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "if_else_1",
                "type": "if_else",
                "config": {
                    "conditions": [
                        {
                            "id": "gt_10",
                            "expression": "{{nodes.start_1.output.value}} > 10",
                        },
                    ],
                },
            },
            {
                "id": "code_a",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"result": value * 2}',
                    "inputs": {"value": "{{nodes.start_1.output.value}}"},
                },
            },
            {
                "id": "code_b",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"result": value + 100}',
                    "inputs": {"value": "{{nodes.start_1.output.value}}"},
                },
            },
            {
                "id": "end_1",
                "type": "end",
                "config": {"output_mapping": {}},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "if_else_1"},
            {"id": "e2", "source": "if_else_1", "target": "code_a", "source_handle": "gt_10"},
            {"id": "e3", "source": "if_else_1", "target": "code_b", "source_handle": "else"},
            {"id": "e4", "source": "code_a", "target": "end_1"},
            {"id": "e5", "source": "code_b", "target": "end_1"},
        ],
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


class TestIfElseTrueBranch:
    """When value > 10 → code_a executes, code_b is skipped."""

    async def test_true_branch_executes(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 15}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        # code_a should have executed
        assert "code_a" in result.executed_node_ids
        # code_b should NOT have executed
        assert "code_b" not in result.executed_node_ids

    async def test_true_branch_outputs(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 15}, repos, wf["id"], ver["id"])

        # code_a: value * 2 = 30
        assert result.pool.get_node_outputs("code_a") == {"result": 30}

    async def test_true_branch_node_runs(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 20}, repos, wf["id"], ver["id"])

        completed_node_ids = {
            nr["node_id"] for nr in result.node_runs if nr["status"] == "completed"
        }
        assert "start_1" in completed_node_ids
        assert "if_else_1" in completed_node_ids
        assert "code_a" in completed_node_ids
        assert "end_1" in completed_node_ids
        # code_b should have no completed node_run
        assert "code_b" not in completed_node_ids

    async def test_boundary_value_11(self, conn: AsyncConnection, repos: Repos) -> None:
        """11 > 10 is true → code_a executes."""
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 11}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        assert "code_a" in result.executed_node_ids
        assert "code_b" not in result.executed_node_ids
        assert result.pool.get_node_outputs("code_a") == {"result": 22}


class TestIfElseElseBranch:
    """When value <= 10 → code_b executes, code_a is skipped."""

    async def test_else_branch_executes(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 5}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        assert "code_b" in result.executed_node_ids
        assert "code_a" not in result.executed_node_ids

    async def test_else_branch_outputs(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 5}, repos, wf["id"], ver["id"])

        # code_b: value + 100 = 105
        assert result.pool.get_node_outputs("code_b") == {"result": 105}

    async def test_boundary_value_10(self, conn: AsyncConnection, repos: Repos) -> None:
        """10 > 10 is false → code_b executes."""
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 10}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        assert "code_b" in result.executed_node_ids
        assert "code_a" not in result.executed_node_ids
        assert result.pool.get_node_outputs("code_b") == {"result": 110}

    async def test_else_branch_events(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _if_else_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"value": 3}, repos, wf["id"], ver["id"])

        event_types = [e["event_type"] for e in result.events]
        assert event_types[0] == "run_started"
        assert event_types[-1] == "run_completed"

        # 4 nodes executed: start_1, if_else_1, code_b, end_1
        node_started_count = sum(1 for t in event_types if t == "node_started")
        node_completed_count = sum(1 for t in event_types if t == "node_completed")
        assert node_started_count == 4
        assert node_completed_count == 4
