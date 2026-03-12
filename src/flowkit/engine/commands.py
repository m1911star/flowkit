"""Command dataclasses for workflow engine operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid

    from flowkit.definition.schema import WorkflowDefinition
    from flowkit.nodes.base import NodeResult


@dataclass
class StartRunCommand:
    run_id: uuid.UUID
    workflow_definition: WorkflowDefinition
    inputs: dict[str, Any]


@dataclass
class CompleteNodeCommand:
    run_id: uuid.UUID
    node_id: str
    result: NodeResult


@dataclass
class PauseRunCommand:
    run_id: uuid.UUID


@dataclass
class ResumeRunCommand:
    run_id: uuid.UUID
    node_id: str | None = None
    inputs: dict[str, Any] | None = None


@dataclass
class CancelRunCommand:
    run_id: uuid.UUID


Command = (
    StartRunCommand | CompleteNodeCommand | PauseRunCommand | ResumeRunCommand | CancelRunCommand
)
