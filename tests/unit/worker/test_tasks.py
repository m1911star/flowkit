"""Unit tests for worker tasks."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from flowkit.runtime.state import NodeState, RunState
from flowkit.worker.tasks import execute_workflow_run, resume_workflow_run

# Sample workflow definition for testing (minimal valid workflow)
SIMPLE_WORKFLOW_DEF = {
    "version": "1.0",
    "metadata": {"name": "test-wf"},
    "nodes": [
        {"id": "start", "type": "start"},
        {"id": "end", "type": "end"},
    ],
    "edges": [
        {"id": "e1", "source": "start", "target": "end"},
    ],
}


@pytest.mark.asyncio
async def test_execute_workflow_run_success():
    """Test successful workflow execution with 3-node workflow."""
    run_id = uuid.uuid4()
    version_id = uuid.uuid4()
    workflow_id = uuid.uuid4()

    # Mock data
    mock_run = {
        "id": run_id,
        "workflow_id": workflow_id,
        "workflow_version_id": version_id,
        "status": RunState.PENDING.value,
        "inputs": {"test_input": "value"},
        "variable_snapshot": None,
    }

    mock_version = {
        "id": version_id,
        "workflow_id": workflow_id,
        "definition": SIMPLE_WORKFLOW_DEF,
    }

    # Mock engine and connection
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock repos
    mock_run_repo = MagicMock()
    mock_run_repo.get = AsyncMock(return_value=mock_run)
    mock_run_repo.update_status = AsyncMock(return_value=True)

    mock_version_repo = MagicMock()
    mock_version_repo.get = AsyncMock(return_value=mock_version)

    mock_node_repo = MagicMock()
    mock_node_repo.create = AsyncMock(
        side_effect=lambda conn, **kwargs: {
            "id": uuid.uuid4(),
            "workflow_run_id": kwargs["workflow_run_id"],
            "node_id": kwargs["node_id"],
            "node_type": kwargs["node_type"],
            "status": NodeState.PENDING.value,
        }
    )
    mock_node_repo.update_status = AsyncMock(return_value=True)

    mock_event_repo = MagicMock()
    mock_event_repo.create = AsyncMock(
        return_value={"id": uuid.uuid4(), "sequence": 1, "event_type": "test"}
    )
    mock_event_repo.get_latest_sequence = AsyncMock(return_value=0)

    # Mock executors - they should return COMPLETED
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(
        return_value=MagicMock(
            status=NodeState.COMPLETED, outputs={"result": 42}, error=None, next_handle="default"
        )
    )

    with (
        patch("flowkit.worker.tasks.get_engine", return_value=mock_engine),
        patch("flowkit.worker.tasks.WorkflowRunRepo", return_value=mock_run_repo),
        patch("flowkit.worker.tasks.WorkflowVersionRepo", return_value=mock_version_repo),
        patch("flowkit.worker.tasks.NodeRunRepo", return_value=mock_node_repo),
        patch("flowkit.worker.tasks.RunEventRepo", return_value=mock_event_repo),
        patch("flowkit.worker.tasks.get_executor", return_value=mock_executor),
    ):
        # Execute the task
        await execute_workflow_run({}, str(run_id))

        # Verify run was updated to RUNNING then COMPLETED
        calls = mock_run_repo.update_status.call_args_list
        assert any(call.kwargs["status"] == RunState.RUNNING.value for call in calls)
        assert any(call.kwargs["status"] == RunState.COMPLETED.value for call in calls)

        # Verify nodes were created (start, end)
        assert mock_node_repo.create.call_count == 2

        # Verify nodes were updated to RUNNING and COMPLETED
        node_status_calls = mock_node_repo.update_status.call_args_list
        assert any(call.kwargs["status"] == NodeState.RUNNING.value for call in node_status_calls)
        assert any(call.kwargs["status"] == NodeState.COMPLETED.value for call in node_status_calls)


@pytest.mark.asyncio
async def test_execute_workflow_run_node_failure():
    """Test workflow execution handles node failure correctly."""
    run_id = uuid.uuid4()
    version_id = uuid.uuid4()
    workflow_id = uuid.uuid4()

    mock_run = {
        "id": run_id,
        "workflow_id": workflow_id,
        "workflow_version_id": version_id,
        "status": RunState.PENDING.value,
        "inputs": {},
        "variable_snapshot": None,
    }

    mock_version = {
        "id": version_id,
        "workflow_id": workflow_id,
        "definition": SIMPLE_WORKFLOW_DEF,
    }

    # Mock engine and connection
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock repos
    mock_run_repo = MagicMock()
    mock_run_repo.get = AsyncMock(return_value=mock_run)
    mock_run_repo.update_status = AsyncMock(return_value=True)

    mock_version_repo = MagicMock()
    mock_version_repo.get = AsyncMock(return_value=mock_version)

    mock_node_repo = MagicMock()
    node_run_counter = {"count": 0}

    def create_node_run(conn: Any, **kwargs: Any) -> dict[str, Any]:
        node_run_counter["count"] += 1
        return {
            "id": uuid.uuid4(),
            "workflow_run_id": kwargs["workflow_run_id"],
            "node_id": kwargs["node_id"],
            "node_type": kwargs["node_type"],
            "status": NodeState.PENDING.value,
        }

    mock_node_repo.create = AsyncMock(side_effect=create_node_run)
    mock_node_repo.update_status = AsyncMock(return_value=True)

    mock_event_repo = MagicMock()
    mock_event_repo.create = AsyncMock(
        return_value={"id": uuid.uuid4(), "sequence": 1, "event_type": "test"}
    )
    mock_event_repo.get_latest_sequence = AsyncMock(return_value=0)

    # Mock executors - second node fails (we'll check for "end" node to fail)
    def mock_execute(ctx: Any) -> Any:
        if ctx.node_def.id == "end":
            return MagicMock(
                status=NodeState.FAILED,
                outputs={},
                error="Node execution failed",
                next_handle="default",
            )
        return MagicMock(status=NodeState.COMPLETED, outputs={}, error=None, next_handle="default")

    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(side_effect=mock_execute)

    with (
        patch("flowkit.worker.tasks.get_engine", return_value=mock_engine),
        patch("flowkit.worker.tasks.WorkflowRunRepo", return_value=mock_run_repo),
        patch("flowkit.worker.tasks.WorkflowVersionRepo", return_value=mock_version_repo),
        patch("flowkit.worker.tasks.NodeRunRepo", return_value=mock_node_repo),
        patch("flowkit.worker.tasks.RunEventRepo", return_value=mock_event_repo),
        patch("flowkit.worker.tasks.get_executor", return_value=mock_executor),
    ):
        # Execute the task
        await execute_workflow_run({}, str(run_id))

        # Verify run was updated to FAILED
        calls = mock_run_repo.update_status.call_args_list
        assert any(
            call.kwargs["status"] == RunState.FAILED.value
            and call.kwargs.get("error") == "Node execution failed"
            for call in calls
        )

        # Verify failed node was updated
        node_status_calls = mock_node_repo.update_status.call_args_list
        assert any(
            call.kwargs["status"] == NodeState.FAILED.value
            and call.kwargs.get("error") == "Node execution failed"
            for call in node_status_calls
        )


@pytest.mark.asyncio
async def test_resume_workflow_run():
    """Test resuming a paused workflow run."""
    run_id = uuid.uuid4()
    version_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    waiting_node_run_id = uuid.uuid4()

    mock_run = {
        "id": run_id,
        "workflow_id": workflow_id,
        "workflow_version_id": version_id,
        "status": RunState.PAUSED.value,
        "inputs": {},
        "variable_snapshot": {
            "workflow_inputs": {},
            "node_outputs": {"start": {}},
        },
    }

    mock_version = {
        "id": version_id,
        "workflow_id": workflow_id,
        "definition": SIMPLE_WORKFLOW_DEF,
    }

    mock_waiting_node_run = {
        "id": waiting_node_run_id,
        "workflow_run_id": run_id,
        "node_id": "end",
        "status": NodeState.WAITING.value,
    }

    # Mock engine and connection
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock repos
    mock_run_repo = MagicMock()
    mock_run_repo.get = AsyncMock(return_value=mock_run)
    mock_run_repo.update_status = AsyncMock(return_value=True)

    mock_version_repo = MagicMock()
    mock_version_repo.get = AsyncMock(return_value=mock_version)

    mock_node_repo = MagicMock()
    mock_node_repo.create = AsyncMock(
        side_effect=lambda conn, **kwargs: {
            "id": uuid.uuid4(),
            "workflow_run_id": kwargs["workflow_run_id"],
            "node_id": kwargs["node_id"],
            "node_type": kwargs["node_type"],
            "status": NodeState.PENDING.value,
        }
    )
    mock_node_repo.update_status = AsyncMock(return_value=True)
    mock_node_repo.get_by_run_and_node = AsyncMock(return_value=mock_waiting_node_run)
    mock_node_repo.list_by_run = AsyncMock(
        return_value=[
            {"node_id": "start", "status": NodeState.COMPLETED.value},
            {"node_id": "end", "status": NodeState.WAITING.value},
        ]
    )

    mock_event_repo = MagicMock()
    mock_event_repo.create = AsyncMock(
        return_value={"id": uuid.uuid4(), "sequence": 1, "event_type": "test"}
    )
    mock_event_repo.get_latest_sequence = AsyncMock(return_value=0)

    # Mock executor - return COMPLETED for all nodes
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(
        return_value=MagicMock(
            status=NodeState.COMPLETED, outputs={}, error=None, next_handle="default"
        )
    )

    with (
        patch("flowkit.worker.tasks.get_engine", return_value=mock_engine),
        patch("flowkit.worker.tasks.WorkflowRunRepo", return_value=mock_run_repo),
        patch("flowkit.worker.tasks.WorkflowVersionRepo", return_value=mock_version_repo),
        patch("flowkit.worker.tasks.NodeRunRepo", return_value=mock_node_repo),
        patch("flowkit.worker.tasks.RunEventRepo", return_value=mock_event_repo),
        patch("flowkit.worker.tasks.get_executor", return_value=mock_executor),
    ):
        # Resume the task with inputs for the waiting node
        await resume_workflow_run({}, str(run_id), "end", {"user_input": "test"})

        # Verify run was updated to RUNNING then COMPLETED
        calls = mock_run_repo.update_status.call_args_list
        assert any(call.kwargs["status"] == RunState.RUNNING.value for call in calls)
        assert any(call.kwargs["status"] == RunState.COMPLETED.value for call in calls)

        # Verify waiting node was updated to COMPLETED
        node_status_calls = mock_node_repo.update_status.call_args_list
        assert any(
            call.args[0] == mock_conn
            and call.args[1] == waiting_node_run_id
            and call.kwargs["status"] == NodeState.COMPLETED.value
            for call in node_status_calls
        )


@pytest.mark.asyncio
async def test_resume_workflow_run_not_paused():
    """Test that resuming a non-paused run raises ValueError."""
    run_id = uuid.uuid4()
    version_id = uuid.uuid4()
    workflow_id = uuid.uuid4()

    mock_run = {
        "id": run_id,
        "workflow_id": workflow_id,
        "workflow_version_id": version_id,
        "status": RunState.RUNNING.value,  # Not paused
        "inputs": {},
        "variable_snapshot": None,
    }

    # Mock engine and connection
    mock_conn = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.begin = MagicMock()
    mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    # Mock repos
    mock_run_repo = MagicMock()
    mock_run_repo.get = AsyncMock(return_value=mock_run)
    mock_run_repo.update_status = AsyncMock(return_value=True)

    mock_event_repo = MagicMock()
    mock_event_repo.create = AsyncMock(
        return_value={"id": uuid.uuid4(), "sequence": 1, "event_type": "test"}
    )
    mock_event_repo.get_latest_sequence = AsyncMock(return_value=0)

    with (
        patch("flowkit.worker.tasks.get_engine", return_value=mock_engine),
        patch("flowkit.worker.tasks.WorkflowRunRepo", return_value=mock_run_repo),
        patch("flowkit.worker.tasks.RunEventRepo", return_value=mock_event_repo),
        pytest.raises(ValueError, match="Cannot resume run"),
    ):
        await resume_workflow_run({}, str(run_id), "end", {})
