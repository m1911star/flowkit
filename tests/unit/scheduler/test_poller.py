"""Tests for flowkit.scheduler.poller — SchedulePoller and compute_next_fire."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.persistence.repos import (
    ScheduleTriggerRepo,
    WorkflowRepo,
    WorkflowRunRepo,
    WorkflowVersionRepo,
)
from flowkit.scheduler.poller import SchedulePoller, compute_next_fire


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def repos() -> tuple[ScheduleTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo]:
    return (
        ScheduleTriggerRepo(),
        WorkflowRepo(),
        WorkflowVersionRepo(),
        WorkflowRunRepo(),
    )


@pytest.fixture
def poller(
    repos: tuple[ScheduleTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
) -> SchedulePoller:
    schedule_repo, _wf_repo, version_repo, run_repo = repos
    return SchedulePoller(
        schedule_repo=schedule_repo,
        version_repo=version_repo,
        run_repo=run_repo,
        poll_interval=1,
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
# compute_next_fire tests
# --------------------------------------------------------------------------- #


class TestComputeNextFire:
    def test_every_minute(self) -> None:
        after = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)
        result = compute_next_fire("* * * * *", "UTC", after)
        assert result == datetime(2026, 3, 11, 12, 1, 0, tzinfo=timezone.utc)

    def test_hourly(self) -> None:
        after = datetime(2026, 3, 11, 12, 30, 0, tzinfo=timezone.utc)
        result = compute_next_fire("0 * * * *", "UTC", after)
        assert result == datetime(2026, 3, 11, 13, 0, 0, tzinfo=timezone.utc)

    def test_daily_at_midnight(self) -> None:
        after = datetime(2026, 3, 11, 0, 0, 0, tzinfo=timezone.utc)
        result = compute_next_fire("0 0 * * *", "UTC", after)
        assert result == datetime(2026, 3, 12, 0, 0, 0, tzinfo=timezone.utc)

    def test_specific_cron(self) -> None:
        # Every weekday at 9:00 AM
        after = datetime(2026, 3, 11, 9, 0, 0, tzinfo=timezone.utc)  # Wednesday
        result = compute_next_fire("0 9 * * 1-5", "UTC", after)
        # Next is Thursday 9:00
        assert result == datetime(2026, 3, 12, 9, 0, 0, tzinfo=timezone.utc)

    def test_result_is_timezone_aware(self) -> None:
        after = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = compute_next_fire("0 0 * * *", "UTC", after)
        assert result.tzinfo is not None


# --------------------------------------------------------------------------- #
# SchedulePoller tests
# --------------------------------------------------------------------------- #


class TestSchedulePoller:
    async def test_poll_once_creates_run_for_due_trigger(
        self,
        conn: AsyncConnection,
        repos: tuple[ScheduleTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        poller: SchedulePoller,
    ) -> None:
        schedule_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)

        # Create a trigger that's already due
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        await schedule_repo.create(
            conn,
            workflow_id=wf_id,
            cron_expression="*/5 * * * *",
            timezone="UTC",
            inputs={"key": "value"},
            next_fire_at=past,
        )

        run_ids = await poller.poll_once(conn)

        assert len(run_ids) == 1
        # Verify run was created
        run = await run_repo.get(conn, run_ids[0])
        assert run is not None
        assert run["workflow_id"] == wf_id
        assert run["trigger_type"] == "schedule"
        assert run["inputs"] == {"key": "value"}

    async def test_poll_once_updates_next_fire_at(
        self,
        conn: AsyncConnection,
        repos: tuple[ScheduleTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        poller: SchedulePoller,
    ) -> None:
        schedule_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        trigger = await schedule_repo.create(
            conn,
            workflow_id=wf_id,
            cron_expression="0 * * * *",  # hourly
            timezone="UTC",
            next_fire_at=past,
        )

        await poller.poll_once(conn)

        # After firing, next_fire_at should be in the future
        from flowkit.persistence.models import schedule_triggers
        import sqlalchemy as sa

        result = await conn.execute(
            sa.select(schedule_triggers.c.next_fire_at, schedule_triggers.c.last_fired_at).where(
                schedule_triggers.c.id == trigger["id"]
            )
        )
        row = result.mappings().first()
        assert row is not None
        assert row["last_fired_at"] is not None
        assert row["next_fire_at"] is not None
        # next_fire_at should be later than the original past time
        # SQLite returns naive datetimes, so strip tzinfo for comparison
        next_fire = row["next_fire_at"]
        past_naive = past.replace(tzinfo=None)
        next_fire_naive = next_fire.replace(tzinfo=None) if next_fire.tzinfo else next_fire
        assert next_fire_naive > past_naive

    async def test_poll_once_no_due_triggers_returns_empty(
        self,
        conn: AsyncConnection,
        repos: tuple[ScheduleTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        poller: SchedulePoller,
    ) -> None:
        schedule_repo, workflow_repo, version_repo, run_repo = repos
        wf_id, ver_id = await _seed_workflow_and_version(conn, workflow_repo, version_repo)

        # Create a trigger that's NOT due yet
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await schedule_repo.create(
            conn,
            workflow_id=wf_id,
            cron_expression="0 * * * *",
            timezone="UTC",
            next_fire_at=future,
        )

        run_ids = await poller.poll_once(conn)
        assert run_ids == []

    async def test_poll_once_handles_multiple_due_triggers(
        self,
        conn: AsyncConnection,
        repos: tuple[ScheduleTriggerRepo, WorkflowRepo, WorkflowVersionRepo, WorkflowRunRepo],
        poller: SchedulePoller,
    ) -> None:
        schedule_repo, workflow_repo, version_repo, run_repo = repos

        past = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Create two workflows with due triggers
        wf_id1, _ = await _seed_workflow_and_version(conn, workflow_repo, version_repo)
        wf_id2, _ = await _seed_workflow_and_version(conn, workflow_repo, version_repo)

        await schedule_repo.create(
            conn,
            workflow_id=wf_id1,
            cron_expression="* * * * *",
            next_fire_at=past,
        )
        await schedule_repo.create(
            conn,
            workflow_id=wf_id2,
            cron_expression="* * * * *",
            next_fire_at=past,
        )

        run_ids = await poller.poll_once(conn)
        assert len(run_ids) == 2
