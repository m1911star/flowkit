"""Tests for flowkit.engine.commands — Command dataclasses."""

import uuid

from flowkit.definition.schema import (
    NodeDef,
    NodeType,
    WorkflowDefinition,
    WorkflowMetadata,
)
from flowkit.engine.commands import (
    CancelRunCommand,
    Command,
    CompleteNodeCommand,
    PauseRunCommand,
    ResumeRunCommand,
    StartRunCommand,
)
from flowkit.nodes.base import NodeResult
from flowkit.runtime.state import NodeState


class TestCommandConstruction:
    def test_start_run_command(self):
        defn = WorkflowDefinition(
            version="1.0",
            metadata=WorkflowMetadata(name="test-wf"),
            nodes=[
                NodeDef(id="start", type=NodeType.start),
                NodeDef(id="end", type=NodeType.end),
            ],
            edges=[],
        )
        run_id = uuid.uuid4()
        cmd = StartRunCommand(run_id=run_id, workflow_definition=defn, inputs={"x": 1})

        assert cmd.run_id == run_id
        assert cmd.workflow_definition is defn
        assert cmd.inputs == {"x": 1}

    def test_complete_node_command(self):
        run_id = uuid.uuid4()
        result = NodeResult(status=NodeState.COMPLETED, outputs={"ok": True})
        cmd = CompleteNodeCommand(run_id=run_id, node_id="fetch", result=result)

        assert cmd.run_id == run_id
        assert cmd.node_id == "fetch"
        assert cmd.result.status == NodeState.COMPLETED

    def test_pause_run_command(self):
        run_id = uuid.uuid4()
        cmd = PauseRunCommand(run_id=run_id)
        assert cmd.run_id == run_id

    def test_resume_run_command_defaults(self):
        run_id = uuid.uuid4()
        cmd = ResumeRunCommand(run_id=run_id)
        assert cmd.node_id is None
        assert cmd.inputs is None

    def test_resume_run_command_with_inputs(self):
        run_id = uuid.uuid4()
        cmd = ResumeRunCommand(run_id=run_id, node_id="approval", inputs={"approved": True})
        assert cmd.node_id == "approval"
        assert cmd.inputs == {"approved": True}

    def test_cancel_run_command(self):
        run_id = uuid.uuid4()
        cmd = CancelRunCommand(run_id=run_id)
        assert cmd.run_id == run_id

    def test_command_union_type(self):
        run_id = uuid.uuid4()
        cmd: Command = PauseRunCommand(run_id=run_id)
        assert isinstance(cmd, PauseRunCommand)
