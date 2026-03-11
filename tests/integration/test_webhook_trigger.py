"""Integration tests — webhook trigger → workflow run creation."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.triggers.webhook import (
    WebhookHandler,
    WebhookInactiveError,
    WebhookNotFoundError,
)
from tests.integration.conftest import (
    Repos,
    create_workflow_and_version,
)


# --------------------------------------------------------------------------- #
# DSL definition (minimal — webhook just creates the run)
# --------------------------------------------------------------------------- #


def _minimal_definition() -> dict[str, Any]:
    """Minimal valid workflow for webhook trigger tests."""
    return {
        "version": "1.0",
        "metadata": {"name": "webhook-target", "description": "webhook trigger test"},
        "inputs": {
            "order_id": {"type": "string", "required": True},
            "amount": {"type": "number", "required": True},
        },
        "outputs": {},
        "nodes": [
            {"id": "start_1", "type": "start", "config": {}},
            {
                "id": "end_1",
                "type": "end",
                "config": {"output_mapping": {}},
            },
        ],
        "edges": [
            {"id": "e1", "source": "start_1", "target": "end_1"},
        ],
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _build_handler(repos: Repos) -> WebhookHandler:
    return WebhookHandler(
        webhook_repo=repos.webhook,
        workflow_repo=repos.workflow,
        version_repo=repos.version,
        run_repo=repos.run,
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


class TestWebhookCreatesRun:
    """Happy path: webhook trigger creates a pending workflow run."""

    async def test_creates_run_with_payload(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _minimal_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        # Create a webhook trigger
        await repos.webhook.create(
            conn,
            workflow_id=wf["id"],
            key="order-webhook",
            input_mapping={"order_id": "id", "amount": "total"},
        )

        handler = _build_handler(repos)
        result = await handler.handle(
            conn,
            key="order-webhook",
            payload={"id": "ORD-123", "total": 99.95},
        )

        assert result["workflow_id"] == wf["id"]
        assert result["status"] == "pending"
        assert result["run_id"] is not None

    async def test_run_has_mapped_inputs(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _minimal_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        await repos.webhook.create(
            conn,
            workflow_id=wf["id"],
            key="order-webhook-2",
            input_mapping={"order_id": "id", "amount": "total"},
        )

        handler = _build_handler(repos)
        result = await handler.handle(
            conn,
            key="order-webhook-2",
            payload={"id": "ORD-456", "total": 42.0},
        )

        # Verify the run was persisted with correct inputs
        db_run = await repos.run.get(conn, result["run_id"])
        assert db_run is not None
        assert db_run["inputs"]["order_id"] == "ORD-456"
        assert db_run["inputs"]["amount"] == 42.0

    async def test_no_mapping_passes_payload_through(
        self, conn: AsyncConnection, repos: Repos
    ) -> None:
        defn = _minimal_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        await repos.webhook.create(
            conn,
            workflow_id=wf["id"],
            key="passthrough-webhook",
            input_mapping=None,
        )

        handler = _build_handler(repos)
        payload = {"order_id": "ORD-789", "amount": 10.0}
        result = await handler.handle(conn, key="passthrough-webhook", payload=payload)

        db_run = await repos.run.get(conn, result["run_id"])
        assert db_run is not None
        assert db_run["inputs"] == payload

    async def test_nested_payload_mapping(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _minimal_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        await repos.webhook.create(
            conn,
            workflow_id=wf["id"],
            key="nested-webhook",
            input_mapping={"order_id": "body.order.id", "amount": "body.order.total"},
        )

        handler = _build_handler(repos)
        result = await handler.handle(
            conn,
            key="nested-webhook",
            payload={"body": {"order": {"id": "ORD-NESTED", "total": 55.55}}},
        )

        db_run = await repos.run.get(conn, result["run_id"])
        assert db_run is not None
        assert db_run["inputs"]["order_id"] == "ORD-NESTED"
        assert db_run["inputs"]["amount"] == 55.55


class TestWebhookErrors:
    """Error cases: unknown key, inactive webhook."""

    async def test_unknown_key_raises(self, conn: AsyncConnection, repos: Repos) -> None:
        handler = _build_handler(repos)

        with pytest.raises(WebhookNotFoundError) as exc_info:
            await handler.handle(conn, key="nonexistent-key")

        assert exc_info.value.key == "nonexistent-key"

    async def test_inactive_webhook_raises(self, conn: AsyncConnection, repos: Repos) -> None:
        defn = _minimal_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        trigger = await repos.webhook.create(
            conn,
            workflow_id=wf["id"],
            key="inactive-webhook",
        )

        # Deactivate the trigger
        await repos.webhook.set_active(conn, trigger["id"], active=False)

        handler = _build_handler(repos)

        with pytest.raises(WebhookInactiveError) as exc_info:
            await handler.handle(conn, key="inactive-webhook")

        assert exc_info.value.key == "inactive-webhook"

    async def test_empty_payload_defaults_to_empty_dict(
        self, conn: AsyncConnection, repos: Repos
    ) -> None:
        """Calling handle with no payload should not crash."""
        defn = _minimal_definition()
        wf, ver = await create_workflow_and_version(conn, repos, defn)

        await repos.webhook.create(
            conn,
            workflow_id=wf["id"],
            key="no-payload-webhook",
        )

        handler = _build_handler(repos)
        result = await handler.handle(conn, key="no-payload-webhook")

        assert result["run_id"] is not None
        assert result["status"] == "pending"
