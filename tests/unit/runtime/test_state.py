"""Tests for flowkit.runtime.state — RunState, NodeState, and transition validation."""

import pytest

from flowkit.runtime.state import (
    VALID_NODE_TRANSITIONS,
    VALID_RUN_TRANSITIONS,
    InvalidTransitionError,
    NodeState,
    RunState,
    transition_node,
    transition_run,
    validate_node_transition,
    validate_run_transition,
)

# ---------------------------------------------------------------------------
# RunState enum
# ---------------------------------------------------------------------------


class TestRunStateEnum:
    def test_has_all_members(self):
        assert set(RunState) == {
            RunState.PENDING,
            RunState.RUNNING,
            RunState.PAUSED,
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
        }

    def test_values_are_lowercase_strings(self):
        assert RunState.PENDING.value == "pending"
        assert RunState.RUNNING.value == "running"
        assert RunState.PAUSED.value == "paused"
        assert RunState.COMPLETED.value == "completed"
        assert RunState.FAILED.value == "failed"
        assert RunState.CANCELLED.value == "cancelled"


# ---------------------------------------------------------------------------
# NodeState enum
# ---------------------------------------------------------------------------


class TestNodeStateEnum:
    def test_has_all_members(self):
        assert set(NodeState) == {
            NodeState.PENDING,
            NodeState.RUNNING,
            NodeState.WAITING,
            NodeState.COMPLETED,
            NodeState.FAILED,
            NodeState.SKIPPED,
        }

    def test_values_are_lowercase_strings(self):
        assert NodeState.PENDING.value == "pending"
        assert NodeState.RUNNING.value == "running"
        assert NodeState.WAITING.value == "waiting"
        assert NodeState.COMPLETED.value == "completed"
        assert NodeState.FAILED.value == "failed"
        assert NodeState.SKIPPED.value == "skipped"


# ---------------------------------------------------------------------------
# VALID_RUN_TRANSITIONS
# ---------------------------------------------------------------------------


class TestValidRunTransitions:
    def test_pending_goes_to_running(self):
        assert VALID_RUN_TRANSITIONS[RunState.PENDING] == {RunState.RUNNING}

    def test_running_goes_to_completed_failed_cancelled_paused(self):
        assert VALID_RUN_TRANSITIONS[RunState.RUNNING] == {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.CANCELLED,
            RunState.PAUSED,
        }

    def test_paused_goes_to_running_cancelled(self):
        assert VALID_RUN_TRANSITIONS[RunState.PAUSED] == {
            RunState.RUNNING,
            RunState.CANCELLED,
        }

    def test_completed_is_terminal(self):
        assert VALID_RUN_TRANSITIONS[RunState.COMPLETED] == set()

    def test_failed_is_terminal(self):
        assert VALID_RUN_TRANSITIONS[RunState.FAILED] == set()

    def test_cancelled_is_terminal(self):
        assert VALID_RUN_TRANSITIONS[RunState.CANCELLED] == set()

    def test_all_states_have_entries(self):
        for state in RunState:
            assert state in VALID_RUN_TRANSITIONS


# ---------------------------------------------------------------------------
# VALID_NODE_TRANSITIONS
# ---------------------------------------------------------------------------


class TestValidNodeTransitions:
    def test_pending_goes_to_running_or_skipped(self):
        assert VALID_NODE_TRANSITIONS[NodeState.PENDING] == {
            NodeState.RUNNING,
            NodeState.SKIPPED,
        }

    def test_running_goes_to_completed_failed_waiting(self):
        assert VALID_NODE_TRANSITIONS[NodeState.RUNNING] == {
            NodeState.COMPLETED,
            NodeState.FAILED,
            NodeState.WAITING,
        }

    def test_waiting_goes_to_running(self):
        assert VALID_NODE_TRANSITIONS[NodeState.WAITING] == {NodeState.RUNNING}

    def test_completed_is_terminal(self):
        assert VALID_NODE_TRANSITIONS[NodeState.COMPLETED] == set()

    def test_failed_is_terminal(self):
        assert VALID_NODE_TRANSITIONS[NodeState.FAILED] == set()

    def test_skipped_is_terminal(self):
        assert VALID_NODE_TRANSITIONS[NodeState.SKIPPED] == set()

    def test_all_states_have_entries(self):
        for state in NodeState:
            assert state in VALID_NODE_TRANSITIONS


# ---------------------------------------------------------------------------
# validate_run_transition
# ---------------------------------------------------------------------------


class TestValidateRunTransition:
    @pytest.mark.parametrize(
        "current,target",
        [
            (RunState.PENDING, RunState.RUNNING),
            (RunState.RUNNING, RunState.COMPLETED),
            (RunState.RUNNING, RunState.FAILED),
            (RunState.RUNNING, RunState.CANCELLED),
            (RunState.RUNNING, RunState.PAUSED),
            (RunState.PAUSED, RunState.RUNNING),
            (RunState.PAUSED, RunState.CANCELLED),
        ],
    )
    def test_valid_transitions_return_true(self, current: RunState, target: RunState):
        assert validate_run_transition(current, target) is True

    @pytest.mark.parametrize(
        "current,target",
        [
            (RunState.PENDING, RunState.COMPLETED),
            (RunState.PENDING, RunState.FAILED),
            (RunState.PENDING, RunState.CANCELLED),
            (RunState.PENDING, RunState.PAUSED),
            (RunState.COMPLETED, RunState.RUNNING),
            (RunState.COMPLETED, RunState.PENDING),
            (RunState.FAILED, RunState.RUNNING),
            (RunState.FAILED, RunState.PENDING),
            (RunState.CANCELLED, RunState.RUNNING),
            (RunState.CANCELLED, RunState.PENDING),
            (RunState.PAUSED, RunState.COMPLETED),
            (RunState.PAUSED, RunState.FAILED),
            (RunState.PAUSED, RunState.PAUSED),
            (RunState.RUNNING, RunState.PENDING),
        ],
    )
    def test_invalid_transitions_return_false(self, current: RunState, target: RunState):
        assert validate_run_transition(current, target) is False

    def test_self_transitions_are_invalid(self):
        for state in RunState:
            assert validate_run_transition(state, state) is False


# ---------------------------------------------------------------------------
# validate_node_transition
# ---------------------------------------------------------------------------


class TestValidateNodeTransition:
    @pytest.mark.parametrize(
        "current,target",
        [
            (NodeState.PENDING, NodeState.RUNNING),
            (NodeState.PENDING, NodeState.SKIPPED),
            (NodeState.RUNNING, NodeState.COMPLETED),
            (NodeState.RUNNING, NodeState.FAILED),
            (NodeState.RUNNING, NodeState.WAITING),
            (NodeState.WAITING, NodeState.RUNNING),
        ],
    )
    def test_valid_transitions_return_true(self, current: NodeState, target: NodeState):
        assert validate_node_transition(current, target) is True

    @pytest.mark.parametrize(
        "current,target",
        [
            (NodeState.PENDING, NodeState.COMPLETED),
            (NodeState.PENDING, NodeState.FAILED),
            (NodeState.PENDING, NodeState.WAITING),
            (NodeState.COMPLETED, NodeState.RUNNING),
            (NodeState.COMPLETED, NodeState.PENDING),
            (NodeState.FAILED, NodeState.RUNNING),
            (NodeState.FAILED, NodeState.PENDING),
            (NodeState.SKIPPED, NodeState.RUNNING),
            (NodeState.SKIPPED, NodeState.PENDING),
            (NodeState.WAITING, NodeState.COMPLETED),
            (NodeState.WAITING, NodeState.FAILED),
            (NodeState.RUNNING, NodeState.PENDING),
            (NodeState.RUNNING, NodeState.SKIPPED),
        ],
    )
    def test_invalid_transitions_return_false(self, current: NodeState, target: NodeState):
        assert validate_node_transition(current, target) is False

    def test_self_transitions_are_invalid(self):
        for state in NodeState:
            assert validate_node_transition(state, state) is False


# ---------------------------------------------------------------------------
# transition_run
# ---------------------------------------------------------------------------


class TestTransitionRun:
    @pytest.mark.parametrize(
        "current,target",
        [
            (RunState.PENDING, RunState.RUNNING),
            (RunState.RUNNING, RunState.COMPLETED),
            (RunState.RUNNING, RunState.FAILED),
            (RunState.RUNNING, RunState.CANCELLED),
            (RunState.RUNNING, RunState.PAUSED),
            (RunState.PAUSED, RunState.RUNNING),
            (RunState.PAUSED, RunState.CANCELLED),
        ],
    )
    def test_valid_transition_returns_target(self, current: RunState, target: RunState):
        assert transition_run(current, target) is target

    def test_invalid_transition_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_run(RunState.COMPLETED, RunState.RUNNING)
        err = exc_info.value
        assert err.current is RunState.COMPLETED
        assert err.target is RunState.RUNNING

    def test_error_message_contains_states(self):
        with pytest.raises(InvalidTransitionError, match="completed.*running"):
            transition_run(RunState.COMPLETED, RunState.RUNNING)

    def test_terminal_states_raise_on_any_transition(self):
        for terminal in (RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED):
            for target in RunState:
                if target is not terminal:
                    with pytest.raises(InvalidTransitionError):
                        transition_run(terminal, target)


# ---------------------------------------------------------------------------
# transition_node
# ---------------------------------------------------------------------------


class TestTransitionNode:
    @pytest.mark.parametrize(
        "current,target",
        [
            (NodeState.PENDING, NodeState.RUNNING),
            (NodeState.PENDING, NodeState.SKIPPED),
            (NodeState.RUNNING, NodeState.COMPLETED),
            (NodeState.RUNNING, NodeState.FAILED),
            (NodeState.RUNNING, NodeState.WAITING),
            (NodeState.WAITING, NodeState.RUNNING),
        ],
    )
    def test_valid_transition_returns_target(self, current: NodeState, target: NodeState):
        assert transition_node(current, target) is target

    def test_invalid_transition_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_node(NodeState.COMPLETED, NodeState.RUNNING)
        err = exc_info.value
        assert err.current is NodeState.COMPLETED
        assert err.target is NodeState.RUNNING

    def test_error_message_contains_states(self):
        with pytest.raises(InvalidTransitionError, match="completed.*running"):
            transition_node(NodeState.COMPLETED, NodeState.RUNNING)

    def test_terminal_states_raise_on_any_transition(self):
        for terminal in (NodeState.COMPLETED, NodeState.FAILED, NodeState.SKIPPED):
            for target in NodeState:
                if target is not terminal:
                    with pytest.raises(InvalidTransitionError):
                        transition_node(terminal, target)


# ---------------------------------------------------------------------------
# InvalidTransitionError
# ---------------------------------------------------------------------------


class TestInvalidTransitionError:
    def test_is_exception(self):
        err = InvalidTransitionError(RunState.COMPLETED, RunState.RUNNING)
        assert isinstance(err, Exception)

    def test_stores_current_and_target(self):
        err = InvalidTransitionError(NodeState.FAILED, NodeState.RUNNING)
        assert err.current is NodeState.FAILED
        assert err.target is NodeState.RUNNING

    def test_str_contains_state_names(self):
        err = InvalidTransitionError(RunState.PAUSED, RunState.COMPLETED)
        msg = str(err)
        assert "paused" in msg
        assert "completed" in msg
