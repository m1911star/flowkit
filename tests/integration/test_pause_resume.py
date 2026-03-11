"""Integration tests — pause / resume / cancel via human_input node."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from tests.integration.conftest import (
    ExecutionResult,
    Repos,
    create_workflow_and_version,
    execute_workflow,
    resume_workflow,
)


# --------------------------------------------------------------------------- #
# DSL definitions
# --------------------------------------------------------------------------- #


def _human_input_definition() -> dict[str, Any]:
    """start → human_input_1 → code_1 (use approved value) → end.

    The human_input node pauses execution. On resume, its outputs are provided
    and code_1 uses them.
    """
    return {
        "version": "1.0",
        "metadata": {"name": "pause-resume", "description": "human input pause/resume test"},
        "inputs": {
            "request": {"type": "string", "required": True},
        },
        "outputs": {},
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "human_input_1",
                "type": "human_input",
                "config": {
                    "prompt": "Please approve the request",
                    "input_schema": {
                        "approved": {"type": "boolean"},
                        "note": {"type": "string"},
                    },
                },
            },
            {
                "id": "code_1",
                "type": "code",
                "config": {
                    "language": "python",
                    "source": 'result = {"status": "approved" if approved else "rejected", "note": note}',
                    "inputs": {
                        "approved": "{{nodes.human_input_1.output.approved}}",
                        "note": "{{nodes.human_input_1.output.note}}",
                    },
                },
            },
            {
                "id": "end_1",
                "type": "end",
                "config": {
                    "output_mapping": {
                        "status": "{{nodes.code_1.output.status}}",
                        "note": "{{nodes.code_1.output.note}}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "human_input_1"},
            {"id": "e2", "source": "human_input_1", "target": "code_1"},
            {"id": "e3", "source": "code_1", "target": "end_1"},
        ],
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


class TestPauseAtHumanInput:
    """Workflow pauses when it hits human_input_1."""

    async def test_workflow_pauses(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        assert result.status == "paused"
        assert result.paused_node_id == "human_input_1"

    async def test_paused_run_db_status(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        db_run = await repos.run.get(conn, result.run["id"])
        assert db_run is not None
        assert db_run["status"] == "paused"

    async def test_executed_nodes_before_pause(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        # start_1 completed, human_input_1 hit (waiting)
        assert "start_1" in result.executed_node_ids
        assert "human_input_1" in result.executed_node_ids
        # code_1 and end_1 should NOT have been reached
        assert "code_1" not in result.executed_node_ids
        assert "end_1" not in result.executed_node_ids

    async def test_pause_emits_waiting_event(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        result = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        event_types = [e["event_type"] for e in result.events]
        assert "node_waiting" in event_types
        # No run_completed since it's paused
        assert "run_completed" not in event_types


class TestResumeAfterPause:
    """Resume a paused workflow with human_input outputs."""

    async def test_resume_completes(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        # First: execute to pause
        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )
        assert paused.status == "paused"

        # Resume with human input
        resumed = await resume_workflow(
            conn,
            defn,
            paused,
            repos,
            human_input_outputs={"approved": True, "note": "LGTM"},
            paused_node_id="human_input_1",
        )

        assert resumed.status == "completed"

    async def test_resume_outputs(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        resumed = await resume_workflow(
            conn,
            defn,
            paused,
            repos,
            human_input_outputs={"approved": True, "note": "ship it"},
            paused_node_id="human_input_1",
        )

        code_outputs = resumed.pool.get_node_outputs("code_1")
        assert code_outputs == {"status": "approved", "note": "ship it"}

    async def test_resume_rejected(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        resumed = await resume_workflow(
            conn,
            defn,
            paused,
            repos,
            human_input_outputs={"approved": False, "note": "not ready"},
            paused_node_id="human_input_1",
        )

        assert resumed.status == "completed"
        code_outputs = resumed.pool.get_node_outputs("code_1")
        assert code_outputs == {"status": "rejected", "note": "not ready"}

    async def test_resume_db_status_completed(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        resumed = await resume_workflow(
            conn,
            defn,
            paused,
            repos,
            human_input_outputs={"approved": True, "note": "ok"},
            paused_node_id="human_input_1",
        )

        db_run = await repos.run.get(conn, resumed.run["id"])
        assert db_run is not None
        assert db_run["status"] == "completed"

    async def test_resume_events_include_run_completed(
        self, conn: AsyncConnection, repos: Repos
    ) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        resumed = await resume_workflow(
            conn,
            defn,
            paused,
            repos,
            human_input_outputs={"approved": True, "note": "done"},
            paused_node_id="human_input_1",
        )

        event_types = [e["event_type"] for e in resumed.events]
        assert "run_completed" in event_types
        assert "run_started" in event_types


class TestCancelPausedWorkflow:
    """Cancel a paused workflow run."""

    async def test_cancel_paused_run(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )
        assert paused.status == "paused"

        # Cancel the run by updating status directly
        await repos.run.update_status(
            conn, paused.run["id"], status="cancelled", expected_status="paused"
        )

        db_run = await repos.run.get(conn, paused.run["id"])
        assert db_run is not None
        assert db_run["status"] == "cancelled"

    async def test_cancel_leaves_node_runs_intact(
        self, conn: AsyncConnection, repos: Repos
    ) -> None:
        defn = _human_input_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        paused = await execute_workflow(
            conn, defn, {"request": "deploy v2"}, repos, wf["id"], ver["id"]
        )

        await repos.run.update_status(
            conn, paused.run["id"], status="cancelled", expected_status="paused"
        )

        # Node runs from before cancel should still be there
        node_runs = await repos.node_run.list_by_run(conn, paused.run["id"])
        assert len(node_runs) >= 2  # start_1 + human_input_1
        node_ids = {nr["node_id"] for nr in node_runs}
        assert "start_1" in node_ids
        assert "human_input_1" in node_ids
