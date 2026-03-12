"""Integration tests — linear workflow execution (start → code → end)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tests.integration.conftest import (
    Repos,
    create_workflow_and_version,
    execute_workflow,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

# --------------------------------------------------------------------------- #
# DSL definitions
# --------------------------------------------------------------------------- #


def _simple_linear_definition() -> dict[str, Any]:
    """start → code_1 (sum a+b) → end."""
    return {
        "version": "1.0",
        "metadata": {"name": "linear-simple", "description": "adds two numbers"},
        "inputs": {
            "a": {"type": "number", "required": True},
            "b": {"type": "number", "required": True},
        },
        "outputs": {
            "sum": {"type": "number", "value": "{{nodes.end_1.output.sum}}"},
        },
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "code_1",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"sum": a + b}',
                    "inputs": {
                        "a": "{{nodes.start_1.output.a}}",
                        "b": "{{nodes.start_1.output.b}}",
                    },
                },
            },
            {
                "id": "end_1",
                "type": "end",
                "config": {
                    "output_mapping": {
                        "sum": "{{nodes.code_1.output.sum}}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "code_1"},
            {"id": "e2", "source": "code_1", "target": "end_1"},
        ],
    }


def _five_node_chain_definition() -> dict[str, Any]:
    """start → code_1 (double) → code_2 (add 10) → code_3 (negate) → end."""
    return {
        "version": "1.0",
        "metadata": {"name": "linear-chain", "description": "five-node chain"},
        "inputs": {
            "x": {"type": "number", "required": True},
        },
        "outputs": {},
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "code_1",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"val": x * 2}',
                    "inputs": {"x": "{{nodes.start_1.output.x}}"},
                },
            },
            {
                "id": "code_2",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"val": val + 10}',
                    "inputs": {"val": "{{nodes.code_1.output.val}}"},
                },
            },
            {
                "id": "code_3",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"val": -val}',
                    "inputs": {"val": "{{nodes.code_2.output.val}}"},
                },
            },
            {
                "id": "end_1",
                "type": "end",
                "config": {
                    "output_mapping": {
                        "final": "{{nodes.code_3.output.val}}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "code_1"},
            {"id": "e2", "source": "code_1", "target": "code_2"},
            {"id": "e3", "source": "code_2", "target": "code_3"},
            {"id": "e4", "source": "code_3", "target": "end_1"},
        ],
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


class TestSimpleLinearWorkflow:
    """start → code (a+b) → end — basic 3-node linear flow."""

    async def test_all_nodes_complete(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _simple_linear_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"a": 5, "b": 3}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        # 3 nodes should have run records
        assert len(result.node_runs) == 3
        assert all(nr["status"] == "completed" for nr in result.node_runs)

    async def test_final_outputs_contain_sum(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _simple_linear_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"a": 5, "b": 3}, repos, wf["id"], ver["id"])

        # code_1 should output {"sum": 8}
        code_outputs = result.pool.get_node_outputs("code_1")
        assert code_outputs == {"sum": 8}

        # end_1 should map it through output_mapping
        end_outputs = result.pool.get_node_outputs("end_1")
        assert end_outputs == {"sum": 8}

    async def test_events_emitted_correctly(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _simple_linear_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"a": 5, "b": 3}, repos, wf["id"], ver["id"])

        event_types = [e["event_type"] for e in result.events]
        # Should have: run_started, then 3 × (node_started, node_completed), then run_completed
        assert event_types[0] == "run_started"
        assert event_types[-1] == "run_completed"

        # Count node events
        node_started_count = sum(1 for t in event_types if t == "node_started")
        node_completed_count = sum(1 for t in event_types if t == "node_completed")
        assert node_started_count == 3
        assert node_completed_count == 3

    async def test_sequences_are_monotonic(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _simple_linear_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"a": 1, "b": 2}, repos, wf["id"], ver["id"])

        sequences = [e["sequence"] for e in result.events]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)  # all unique

    async def test_different_inputs(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _simple_linear_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(
            conn, defn, {"a": 100, "b": -50}, repos, wf["id"], ver["id"]
        )

        assert result.status == "completed"
        assert result.pool.get_node_outputs("code_1") == {"sum": 50}

    async def test_run_persisted_in_db(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _simple_linear_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"a": 5, "b": 3}, repos, wf["id"], ver["id"])

        # Verify run record in DB
        db_run = await repos.run.get(conn, result.run["id"])
        assert db_run is not None
        assert db_run["status"] == "completed"


class TestFiveNodeChain:
    """start → code_1 (×2) → code_2 (+10) → code_3 (negate) → end."""

    async def test_chain_computation(self, conn: AsyncConnection, repos: Repos) -> None:
        """Input x=5 → 5*2=10 → 10+10=20 → -20."""
        defn = _five_node_chain_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"x": 5}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        assert len(result.node_runs) == 5
        assert result.pool.get_node_outputs("code_1") == {"val": 10}
        assert result.pool.get_node_outputs("code_2") == {"val": 20}
        assert result.pool.get_node_outputs("code_3") == {"val": -20}
        assert result.pool.get_node_outputs("end_1") == {"final": -20}

    async def test_all_nodes_completed_in_order(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _five_node_chain_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"x": 3}, repos, wf["id"], ver["id"])

        assert all(nr["status"] == "completed" for nr in result.node_runs)
        # Verify ordering: each node_run should have a node_id in the expected order
        node_ids = [nr["node_id"] for nr in result.node_runs]
        assert node_ids == ["start_1", "code_1", "code_2", "code_3", "end_1"]

    async def test_chain_with_zero(self, conn: AsyncConnection, repos: Repos) -> None:
        """Input x=0 → 0*2=0 → 0+10=10 → -10."""
        defn = _five_node_chain_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"x": 0}, repos, wf["id"], ver["id"])

        assert result.status == "completed"
        assert result.pool.get_node_outputs("code_3") == {"val": -10}
        assert result.pool.get_node_outputs("end_1") == {"final": -10}

    async def test_chain_events_count(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _five_node_chain_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(conn, defn, {"x": 1}, repos, wf["id"], ver["id"])

        event_types = [e["event_type"] for e in result.events]
        # 1 run_started + 5*(node_started + node_completed) + 1 run_completed = 12
        assert len(event_types) == 12
