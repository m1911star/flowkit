"""Tests for flowkit.triggers.webhook — WebhookHandler."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.persistence.repos import (
    WebhookTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)
from flowkit.triggers.webhook import (
    WebhookHandler,
    WebhookInactiveError,
    WebhookNotFoundError,
    _apply_input_mapping,
    _resolve_path,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def repos() -> tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo]:
    return (
        WebhookTriggerRepo(),
        WorkflowRepo(),
        WorkflowVersionRepo(),
        WorkflowRunRepo(),
    )


@pytest.fixture
def handler(
    repos: tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
) -> WebhookHandler:
    webhook_repo, workflow_repo, version_repo, run_repo = repos
    return WebhookHandler(
        webhook_repo=webhook_repo,
        workflow_repo=workflow_repo,
        version_repo=version_repo,
        run_repo=run_repo,
    )


async def _seed_workflow_and_version(
    conn: AsyncConnection,
    workflow_repo: WorkflowRepo,
    version_repo: WorkflowVersionRepo,
    *,
    publish: bool = True,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper: create a workflow + version, optionally published."""
    wf = await workflow_repo.create(conn, name=f"wf-{uuid.uuid4().hex[:8]}")
    ver = await version_repo.create(
        conn,
        workflow_id=wf["id"],
        version=1,
        definition={"nodes": [], "edges": []},
        checksum="abc123",
        is_published=publish,
    )
    return wf["id"], ver["id"]


# --------------------------------------------------------------------------- #
# WebhookHandler tests
# --------------------------------------------------------------------------- #


class TestWebhookHandler:
    async def test_handle_creates_run(
        self,
        conn: AsyncConnection,
        repos: tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        handler: WebhookHandler,
    ) -> None:
        webhook_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)
        await webhook_repo.create(conn, workflow_id=wf_id, key="my-hook")

        result = await handler.handle(conn, "my-hook", payload={"foo": "bar"})

        assert "run_id" in result
        assert result["workflow_id"] == wf_id
        assert result["status"] == "pending"

        # Verify the run was actually persisted
        run = await run_repo.get(conn, result["run_id"])
        assert run is not None
        assert run["trigger_type"] == "webhook"

    async def test_handle_unknown_key_raises(
        self,
        conn: AsyncConnection,
        handler: WebhookHandler,
    ) -> None:
        with pytest.raises(WebhookNotFoundError) as exc_info:
            await handler.handle(conn, "nonexistent-key")
        assert exc_info.value.key == "nonexistent-key"

    async def test_handle_inactive_webhook_raises(
        self,
        conn: AsyncConnection,
        repos: tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        handler: WebhookHandler,
    ) -> None:
        webhook_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)
        trigger = await webhook_repo.create(conn, workflow_id=wf_id, key="inactive-hook")
        await webhook_repo.set_active(conn, trigger["id"], active=False)

        with pytest.raises(WebhookInactiveError) as exc_info:
            await handler.handle(conn, "inactive-hook")
        assert exc_info.value.key == "inactive-hook"

    async def test_handle_with_input_mapping(
        self,
        conn: AsyncConnection,
        repos: tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        handler: WebhookHandler,
    ) -> None:
        webhook_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)
        mapping = {"order_id": "$.body.order.id", "priority": "$.body.priority"}
        await webhook_repo.create(conn, workflow_id=wf_id, key="mapped-hook", input_mapping=mapping)

        payload = {
            "body": {
                "order": {"id": "ORD-123"},
                "priority": "high",
            }
        }
        result = await handler.handle(conn, "mapped-hook", payload=payload)

        # Check the created run has the mapped inputs
        run = await run_repo.get(conn, result["run_id"])
        assert run is not None
        assert run["inputs"] == {"order_id": "ORD-123", "priority": "high"}

    async def test_handle_falls_back_to_latest_version(
        self,
        conn: AsyncConnection,
        repos: tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        handler: WebhookHandler,
    ) -> None:
        """If no published version exists, fall back to the latest version."""
        webhook_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(
            conn, workflow_repo, version_repo, publish=False
        )
        await webhook_repo.create(conn, workflow_id=wf_id, key="latest-hook")

        result = await handler.handle(conn, "latest-hook")
        assert result["status"] == "pending"

    async def test_handle_without_payload(
        self,
        conn: AsyncConnection,
        repos: tuple[WebhookTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        handler: WebhookHandler,
    ) -> None:
        webhook_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)
        await webhook_repo.create(conn, workflow_id=wf_id, key="no-payload")

        result = await handler.handle(conn, "no-payload")
        assert result["status"] == "pending"


# --------------------------------------------------------------------------- #
# Input mapping helper tests
# --------------------------------------------------------------------------- #


class TestInputMapping:
    def test_apply_mapping_simple(self) -> None:
        mapping = {"user": "$.name", "age": "$.profile.age"}
        payload = {"name": "Alice", "profile": {"age": 30}}
        result = _apply_input_mapping(mapping, payload)
        assert result == {"user": "Alice", "age": 30}

    def test_apply_mapping_none_returns_payload(self) -> None:
        payload = {"x": 1}
        result = _apply_input_mapping(None, payload)
        assert result == {"x": 1}

    def test_apply_mapping_empty_returns_payload(self) -> None:
        payload = {"x": 1}
        result = _apply_input_mapping({}, payload)
        assert result == {"x": 1}

    def test_resolve_path_missing_key(self) -> None:
        result = _resolve_path({"a": 1}, "$.b")
        assert result is None

    def test_resolve_path_nested(self) -> None:
        data = {"a": {"b": {"c": 42}}}
        assert _resolve_path(data, "$.a.b.c") == 42

    def test_resolve_path_without_dollar_prefix(self) -> None:
        data = {"x": 10}
        assert _resolve_path(data, "x") == 10
