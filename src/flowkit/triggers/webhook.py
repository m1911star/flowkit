"""Webhook trigger handler.

Looks up a webhook trigger by its unique key, applies input mapping,
and creates a new workflow run.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.persistence.repos import (
    WebhookTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class WebhookNotFoundError(Exception):
    """Raised when no webhook trigger matches the given key."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Webhook trigger not found for key: {key}")


class WebhookInactiveError(Exception):
    """Raised when the matching webhook trigger is deactivated."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Webhook trigger is inactive for key: {key}")


# --------------------------------------------------------------------------- #
# WebhookHandler
# --------------------------------------------------------------------------- #
class WebhookHandler:
    """Process incoming webhook requests and create workflow runs."""

    def __init__(
        self,
        webhook_repo: WebhookTriggerRepo,
        workflow_repo: WorkflowRepo,
        version_repo: WorkflowVersionRepo,
        run_repo: WorkflowRunRepo,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._workflow_repo = workflow_repo
        self._version_repo = version_repo
        self._run_repo = run_repo

    async def handle(
        self,
        conn: AsyncConnection,
        key: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle an incoming webhook request.

        1. Look up the trigger by *key*.
        2. Validate it exists and is active.
        3. Resolve the published (or latest) workflow version.
        4. Apply ``input_mapping`` to the payload to produce workflow inputs.
        5. Create a workflow run.

        Returns ``{"run_id": UUID, "workflow_id": UUID, "status": "pending"}``.
        """
        # 1. Lookup trigger
        trigger = await self._webhook_repo.get_by_key(conn, key)
        if trigger is None:
            raise WebhookNotFoundError(key)

        # 2. Check active
        if not trigger["is_active"]:
            raise WebhookInactiveError(key)

        workflow_id: uuid.UUID = trigger["workflow_id"]

        # 3. Get published version, fall back to latest
        version = await self._version_repo.get_published(conn, workflow_id)
        if version is None:
            version = await self._version_repo.get_latest(conn, workflow_id)
        if version is None:
            raise ValueError(f"No workflow version found for workflow {workflow_id}")

        # 4. Apply input mapping
        inputs = _apply_input_mapping(
            trigger.get("input_mapping"),
            payload or {},
        )

        # 5. Create workflow run
        run = await self._run_repo.create(
            conn,
            workflow_id=workflow_id,
            workflow_version_id=version["id"],
            inputs=inputs,
            trigger_type="webhook",
            trigger_id=trigger["id"],
        )

        return {
            "run_id": run["id"],
            "workflow_id": workflow_id,
            "status": run["status"],
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _apply_input_mapping(
    mapping: dict[str, str] | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Map webhook payload fields to workflow input keys.

    The mapping is a simple ``{workflow_input_key: payload_key}`` dict.
    Nested access is supported via dot notation (e.g. ``"body.order.id"``).

    Returns the mapped inputs dict.
    """
    if not mapping:
        return payload

    inputs: dict[str, Any] = {}
    for workflow_key, payload_path in mapping.items():
        value = _resolve_path(payload, payload_path)
        if value is not None:
            inputs[workflow_key] = value
    return inputs


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    """Resolve a dot-separated path against *data*.

    A leading ``$.`` is stripped for convenience (JSONPath-like syntax from the spec).
    """
    # Strip leading $. if present
    if path.startswith("$."):
        path = path[2:]

    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
