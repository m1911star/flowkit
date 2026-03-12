"""Run and node state machines with transition validation.

This module is pure Python with zero external dependencies.
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunState(StrEnum):
    """Lifecycle states for a workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeState(StrEnum):
    """Lifecycle states for a single node execution within a run."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Valid transition tables
# ---------------------------------------------------------------------------

VALID_RUN_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.PENDING: {RunState.RUNNING},
    RunState.RUNNING: {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED, RunState.PAUSED},
    RunState.PAUSED: {RunState.RUNNING, RunState.CANCELLED},
    RunState.COMPLETED: set(),
    RunState.FAILED: set(),
    RunState.CANCELLED: set(),
}

VALID_NODE_TRANSITIONS: dict[NodeState, set[NodeState]] = {
    NodeState.PENDING: {NodeState.RUNNING, NodeState.SKIPPED},
    NodeState.RUNNING: {NodeState.COMPLETED, NodeState.FAILED, NodeState.WAITING},
    NodeState.WAITING: {NodeState.RUNNING},
    NodeState.COMPLETED: set(),
    NodeState.FAILED: set(),
    NodeState.SKIPPED: set(),
}


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: RunState | NodeState, target: RunState | NodeState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid state transition: {current.value!r} → {target.value!r}")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_run_transition(current: RunState, target: RunState) -> bool:
    """Return True if *current → target* is a valid run state transition."""
    return target in VALID_RUN_TRANSITIONS[current]


def validate_node_transition(current: NodeState, target: NodeState) -> bool:
    """Return True if *current → target* is a valid node state transition."""
    return target in VALID_NODE_TRANSITIONS[current]


# ---------------------------------------------------------------------------
# Transition functions
# ---------------------------------------------------------------------------


def transition_run(current: RunState, target: RunState) -> RunState:
    """Transition a run state, raising on invalid moves.

    Returns *target* on success.
    Raises ``InvalidTransitionError`` if the transition is not allowed.
    """
    if not validate_run_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target


def transition_node(current: NodeState, target: NodeState) -> NodeState:
    """Transition a node state, raising on invalid moves.

    Returns *target* on success.
    Raises ``InvalidTransitionError`` if the transition is not allowed.
    """
    if not validate_node_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target
