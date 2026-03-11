"""Tests for repository layer — all 7 repos."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.persistence.repos import (
    NodeRunRepo,
    RunEventRepo,
    ScheduleTriggerRepo,
    WebhookTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)


# --------------------------------------------------------------------------- #
# WorkflowRepo
# --------------------------------------------------------------------------- #
class TestWorkflowRepo:
    @pytest.fixture
    def repo(self) -> WorkflowRepo:
        return WorkflowRepo()

    async def test_create_and_get(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        wf = await repo.create(conn, name="test-wf", description="A test workflow")
        assert wf["name"] == "test-wf"
        assert wf["description"] == "A test workflow"
        assert wf["id"] is not None

        fetched = await repo.get(conn, wf["id"])
        assert fetched is not None
        assert fetched["name"] == "test-wf"

    async def test_get_nonexistent(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        result = await repo.get(conn, uuid.uuid4())
        assert result is None

    async def test_list_all(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        await repo.create(conn, name="wf-1")
        await repo.create(conn, name="wf-2")
        all_wfs = await repo.list_all(conn)
        assert len(all_wfs) == 2

    async def test_list_with_limit(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        for i in range(5):
            await repo.create(conn, name=f"wf-{i}")
        result = await repo.list_all(conn, limit=3)
        assert len(result) == 3

    async def test_update(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        wf = await repo.create(conn, name="old-name")
        updated = await repo.update(conn, wf["id"], name="new-name")
        assert updated is True
        fetched = await repo.get(conn, wf["id"])
        assert fetched is not None
        assert fetched["name"] == "new-name"

    async def test_update_nonexistent(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        updated = await repo.update(conn, uuid.uuid4(), name="x")
        assert updated is False

    async def test_delete(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        wf = await repo.create(conn, name="to-delete")
        deleted = await repo.delete(conn, wf["id"])
        assert deleted is True
        assert await repo.get(conn, wf["id"]) is None

    async def test_delete_nonexistent(self, repo: WorkflowRepo, conn: AsyncConnection) -> None:
        deleted = await repo.delete(conn, uuid.uuid4())
        assert deleted is False


# --------------------------------------------------------------------------- #
# WorkflowVersionRepo
# --------------------------------------------------------------------------- #
class TestWorkflowVersionRepo:
    @pytest.fixture
    def repo(self) -> WorkflowVersionRepo:
        return WorkflowVersionRepo()

    @pytest.fixture
    async def workflow_id(self, conn: AsyncConnection) -> uuid.UUID:
        wf = await WorkflowRepo().create(conn, name="versioned-wf")
        return wf["id"]

    async def test_create_and_get(
        self,
        repo: WorkflowVersionRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        ver = await repo.create(
            conn,
            workflow_id=workflow_id,
            version=1,
            definition={"version": "1.0"},
            checksum="abc123",
        )
        assert ver["version"] == 1
        assert ver["definition"] == {"version": "1.0"}

        fetched = await repo.get(conn, ver["id"])
        assert fetched is not None
        assert fetched["checksum"] == "abc123"

    async def test_get_by_workflow_and_version(
        self,
        repo: WorkflowVersionRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        await repo.create(
            conn,
            workflow_id=workflow_id,
            version=1,
            definition={},
            checksum="a",
        )
        result = await repo.get_by_workflow_and_version(conn, workflow_id, 1)
        assert result is not None
        assert result["version"] == 1

    async def test_get_latest(
        self,
        repo: WorkflowVersionRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        await repo.create(conn, workflow_id=workflow_id, version=1, definition={}, checksum="a")
        await repo.create(conn, workflow_id=workflow_id, version=2, definition={}, checksum="b")
        latest = await repo.get_latest(conn, workflow_id)
        assert latest is not None
        assert latest["version"] == 2

    async def test_get_published(
        self,
        repo: WorkflowVersionRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        ver = await repo.create(
            conn,
            workflow_id=workflow_id,
            version=1,
            definition={},
            checksum="a",
            is_published=True,
        )
        published = await repo.get_published(conn, workflow_id)
        assert published is not None
        assert published["id"] == ver["id"]

    async def test_publish(
        self,
        repo: WorkflowVersionRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        ver = await repo.create(
            conn,
            workflow_id=workflow_id,
            version=1,
            definition={},
            checksum="a",
        )
        assert ver["is_published"] is False
        result = await repo.publish(conn, ver["id"])
        assert result is True

    async def test_list_by_workflow(
        self,
        repo: WorkflowVersionRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        await repo.create(conn, workflow_id=workflow_id, version=1, definition={}, checksum="a")
        await repo.create(conn, workflow_id=workflow_id, version=2, definition={}, checksum="b")
        versions = await repo.list_by_workflow(conn, workflow_id)
        assert len(versions) == 2
        assert versions[0]["version"] == 2  # desc order


# --------------------------------------------------------------------------- #
# WorkflowRunRepo
# --------------------------------------------------------------------------- #
class TestWorkflowRunRepo:
    @pytest.fixture
    def repo(self) -> WorkflowRunRepo:
        return WorkflowRunRepo()

    @pytest.fixture
    async def workflow_ids(self, conn: AsyncConnection) -> tuple[uuid.UUID, uuid.UUID]:
        wf = await WorkflowRepo().create(conn, name="run-wf")
        ver = await WorkflowVersionRepo().create(
            conn,
            workflow_id=wf["id"],
            version=1,
            definition={},
            checksum="x",
        )
        return wf["id"], ver["id"]

    async def test_create_and_get(
        self,
        repo: WorkflowRunRepo,
        conn: AsyncConnection,
        workflow_ids: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        wf_id, ver_id = workflow_ids
        run = await repo.create(
            conn, workflow_id=wf_id, workflow_version_id=ver_id, inputs={"x": 1}
        )
        assert run["status"] == "pending"
        assert run["inputs"] == {"x": 1}

        fetched = await repo.get(conn, run["id"])
        assert fetched is not None
        assert fetched["status"] == "pending"

    async def test_update_status(
        self,
        repo: WorkflowRunRepo,
        conn: AsyncConnection,
        workflow_ids: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        wf_id, ver_id = workflow_ids
        run = await repo.create(conn, workflow_id=wf_id, workflow_version_id=ver_id)
        updated = await repo.update_status(
            conn,
            run["id"],
            status="running",
            expected_status="pending",
        )
        assert updated is True

    async def test_update_status_optimistic_lock_fail(
        self,
        repo: WorkflowRunRepo,
        conn: AsyncConnection,
        workflow_ids: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        wf_id, ver_id = workflow_ids
        run = await repo.create(conn, workflow_id=wf_id, workflow_version_id=ver_id)
        # Expect "running" but actual is "pending"
        updated = await repo.update_status(
            conn,
            run["id"],
            status="completed",
            expected_status="running",
        )
        assert updated is False

    async def test_list_by_workflow(
        self,
        repo: WorkflowRunRepo,
        conn: AsyncConnection,
        workflow_ids: tuple[uuid.UUID, uuid.UUID],
    ) -> None:
        wf_id, ver_id = workflow_ids
        await repo.create(conn, workflow_id=wf_id, workflow_version_id=ver_id)
        await repo.create(conn, workflow_id=wf_id, workflow_version_id=ver_id)
        runs = await repo.list_by_workflow(conn, wf_id)
        assert len(runs) == 2


# --------------------------------------------------------------------------- #
# NodeRunRepo
# --------------------------------------------------------------------------- #
class TestNodeRunRepo:
    @pytest.fixture
    def repo(self) -> NodeRunRepo:
        return NodeRunRepo()

    @pytest.fixture
    async def run_id(self, conn: AsyncConnection) -> uuid.UUID:
        wf = await WorkflowRepo().create(conn, name="node-run-wf")
        ver = await WorkflowVersionRepo().create(
            conn,
            workflow_id=wf["id"],
            version=1,
            definition={},
            checksum="x",
        )
        run = await WorkflowRunRepo().create(
            conn,
            workflow_id=wf["id"],
            workflow_version_id=ver["id"],
        )
        return run["id"]

    async def test_create_and_get(
        self,
        repo: NodeRunRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        nr = await repo.create(conn, workflow_run_id=run_id, node_id="start", node_type="start")
        assert nr["status"] == "pending"
        assert nr["node_id"] == "start"

        fetched = await repo.get(conn, nr["id"])
        assert fetched is not None

    async def test_get_by_run_and_node(
        self,
        repo: NodeRunRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        await repo.create(conn, workflow_run_id=run_id, node_id="start", node_type="start")
        result = await repo.get_by_run_and_node(conn, run_id, "start")
        assert result is not None
        assert result["node_id"] == "start"

    async def test_update_status(
        self,
        repo: NodeRunRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        nr = await repo.create(conn, workflow_run_id=run_id, node_id="start", node_type="start")
        updated = await repo.update_status(conn, nr["id"], status="running")
        assert updated is True

    async def test_list_by_run(
        self,
        repo: NodeRunRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        await repo.create(conn, workflow_run_id=run_id, node_id="start", node_type="start")
        await repo.create(conn, workflow_run_id=run_id, node_id="end", node_type="end")
        nodes = await repo.list_by_run(conn, run_id)
        assert len(nodes) == 2


# --------------------------------------------------------------------------- #
# RunEventRepo
# --------------------------------------------------------------------------- #
class TestRunEventRepo:
    @pytest.fixture
    def repo(self) -> RunEventRepo:
        return RunEventRepo()

    @pytest.fixture
    async def run_id(self, conn: AsyncConnection) -> uuid.UUID:
        wf = await WorkflowRepo().create(conn, name="event-wf")
        ver = await WorkflowVersionRepo().create(
            conn,
            workflow_id=wf["id"],
            version=1,
            definition={},
            checksum="x",
        )
        run = await WorkflowRunRepo().create(
            conn,
            workflow_id=wf["id"],
            workflow_version_id=ver["id"],
        )
        return run["id"]

    async def test_create_and_list(
        self,
        repo: RunEventRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        await repo.create(conn, workflow_run_id=run_id, sequence=1, event_type="run_started")
        await repo.create(
            conn,
            workflow_run_id=run_id,
            sequence=2,
            event_type="node_started",
            node_id="start",
        )
        events = await repo.list_by_run(conn, run_id)
        assert len(events) == 2
        assert events[0]["sequence"] == 1
        assert events[1]["sequence"] == 2

    async def test_list_after_sequence(
        self,
        repo: RunEventRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        await repo.create(conn, workflow_run_id=run_id, sequence=1, event_type="run_started")
        await repo.create(
            conn, workflow_run_id=run_id, sequence=2, event_type="node_started", node_id="s"
        )
        await repo.create(
            conn, workflow_run_id=run_id, sequence=3, event_type="node_completed", node_id="s"
        )
        events = await repo.list_by_run(conn, run_id, after_sequence=1)
        assert len(events) == 2
        assert events[0]["sequence"] == 2

    async def test_get_latest_sequence(
        self,
        repo: RunEventRepo,
        conn: AsyncConnection,
        run_id: uuid.UUID,
    ) -> None:
        assert await repo.get_latest_sequence(conn, run_id) == 0
        await repo.create(conn, workflow_run_id=run_id, sequence=1, event_type="run_started")
        await repo.create(
            conn, workflow_run_id=run_id, sequence=2, event_type="node_started", node_id="s"
        )
        assert await repo.get_latest_sequence(conn, run_id) == 2


# --------------------------------------------------------------------------- #
# WebhookTriggerRepo
# --------------------------------------------------------------------------- #
class TestWebhookTriggerRepo:
    @pytest.fixture
    def repo(self) -> WebhookTriggerRepo:
        return WebhookTriggerRepo()

    @pytest.fixture
    async def workflow_id(self, conn: AsyncConnection) -> uuid.UUID:
        wf = await WorkflowRepo().create(conn, name="webhook-wf")
        return wf["id"]

    async def test_create_and_get_by_key(
        self,
        repo: WebhookTriggerRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        trigger = await repo.create(conn, workflow_id=workflow_id, key="my-hook")
        assert trigger["key"] == "my-hook"
        assert trigger["is_active"] is True

        fetched = await repo.get_by_key(conn, "my-hook")
        assert fetched is not None
        assert fetched["workflow_id"] == workflow_id

    async def test_get_by_key_nonexistent(
        self,
        repo: WebhookTriggerRepo,
        conn: AsyncConnection,
    ) -> None:
        result = await repo.get_by_key(conn, "nope")
        assert result is None

    async def test_set_active(
        self,
        repo: WebhookTriggerRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        trigger = await repo.create(conn, workflow_id=workflow_id, key="toggle-hook")
        result = await repo.set_active(conn, trigger["id"], active=False)
        assert result is True


# --------------------------------------------------------------------------- #
# ScheduleTriggerRepo
# --------------------------------------------------------------------------- #
class TestScheduleTriggerRepo:
    @pytest.fixture
    def repo(self) -> ScheduleTriggerRepo:
        return ScheduleTriggerRepo()

    @pytest.fixture
    async def workflow_id(self, conn: AsyncConnection) -> uuid.UUID:
        wf = await WorkflowRepo().create(conn, name="schedule-wf")
        return wf["id"]

    async def test_create(
        self,
        repo: ScheduleTriggerRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        now = datetime.now(timezone.utc)
        trigger = await repo.create(
            conn,
            workflow_id=workflow_id,
            cron_expression="0 * * * *",
            next_fire_at=now,
        )
        assert trigger["cron_expression"] == "0 * * * *"
        assert trigger["is_active"] is True

    async def test_get_due_triggers(
        self,
        repo: ScheduleTriggerRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await repo.create(
            conn,
            workflow_id=workflow_id,
            cron_expression="0 * * * *",
            next_fire_at=past,
        )
        await repo.create(
            conn,
            workflow_id=workflow_id,
            cron_expression="0 0 * * *",
            next_fire_at=future,
        )
        now = datetime.now(timezone.utc)
        due = await repo.get_due_triggers(conn, now)
        assert len(due) == 1
        assert due[0]["cron_expression"] == "0 * * * *"

    async def test_update_after_fire(
        self,
        repo: ScheduleTriggerRepo,
        conn: AsyncConnection,
        workflow_id: uuid.UUID,
    ) -> None:
        now = datetime.now(timezone.utc)
        trigger = await repo.create(
            conn,
            workflow_id=workflow_id,
            cron_expression="0 * * * *",
            next_fire_at=now,
        )
        next_fire = now + timedelta(hours=1)
        updated = await repo.update_after_fire(
            conn,
            trigger["id"],
            last_fired_at=now,
            next_fire_at=next_fire,
        )
        assert updated is True
