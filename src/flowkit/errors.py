"""Structured error hierarchy for flowkit.

Every flowkit exception carries a machine-readable ``code`` and optional
``details`` dict, enabling consistent API error responses and dead-letter
tracking.
"""

from __future__ import annotations

from typing import Any


class FlowkitError(Exception):
    """Base exception for all flowkit errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details: dict[str, Any] = details or {}


class NotFoundError(FlowkitError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} '{identifier}' not found",
            code="NOT_FOUND",
            details={"resource": resource, "id": identifier},
        )


class ValidationError(FlowkitError):
    """Raised when input validation fails."""

    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        super().__init__(
            message,
            code="VALIDATION_ERROR",
            details={"errors": errors or []},
        )


class ExecutionError(FlowkitError):
    """Raised when a workflow execution step fails."""

    def __init__(
        self,
        message: str,
        *,
        node_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="EXECUTION_ERROR",
            details={"node_id": node_id, "run_id": run_id},
        )


class TimeoutError(FlowkitError):  # noqa: A001
    """Raised when an operation exceeds its time budget."""

    def __init__(self, message: str, *, timeout_seconds: int) -> None:
        super().__init__(
            message,
            code="TIMEOUT",
            details={"timeout_seconds": timeout_seconds},
        )


class WebhookError(FlowkitError):
    """Raised for webhook-related failures."""

    def __init__(self, message: str, *, key: str | None = None) -> None:
        super().__init__(
            message,
            code="WEBHOOK_ERROR",
            details={"key": key},
        )


class StateTransitionError(FlowkitError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, message: str, *, current: str, target: str) -> None:
        super().__init__(
            message,
            code="INVALID_TRANSITION",
            details={"current": current, "target": target},
        )
