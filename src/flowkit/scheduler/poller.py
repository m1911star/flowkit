"""Schedule trigger poller — DB polling loop for cron-based triggers.

The scheduler service runs a single ``SchedulePoller`` that periodically
queries the ``schedule_triggers`` table for due triggers, creates
workflow runs, and advances the ``next_fire_at`` timestamp using croniter.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from croniter import croniter

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncConnection

    from flowkit.persistence.repos import (
        ScheduleTriggerRepo,
        WorkflowRunRepo,
        WorkflowVersionRepo,
    )

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helper: compute next fire time
# --------------------------------------------------------------------------- #


def compute_next_fire(
    cron_expression: str,
    tz: str,
    after: datetime,
) -> datetime:
    """Compute the next fire time after *after* for a cron expression.

    The returned datetime is always UTC-aware regardless of the trigger's
    configured timezone (``tz`` param affects cron evaluation only via
    croniter's own handling).
    """
    # croniter works with the provided datetime directly
    cron = croniter(cron_expression, after)
    next_dt: datetime = cron.get_next(datetime)
    # Ensure the result is timezone-aware (UTC)
    if next_dt.tzinfo is None:
        next_dt = next_dt.replace(tzinfo=UTC)
    return next_dt


# --------------------------------------------------------------------------- #
# SchedulePoller
# --------------------------------------------------------------------------- #


class SchedulePoller:
    """Poll the schedule_triggers table and fire due triggers."""

    def __init__(
        self,
        schedule_repo: ScheduleTriggerRepo,
        version_repo: WorkflowVersionRepo,
        run_repo: WorkflowRunRepo,
        poll_interval: int = 15,
    ) -> None:
        self._schedule_repo = schedule_repo
        self._version_repo = version_repo
        self._run_repo = run_repo
        self.poll_interval = poll_interval
        self._shutdown_event = asyncio.Event()

    async def poll_once(self, conn: AsyncConnection) -> list[uuid.UUID]:
        """Check for due triggers and create runs.

        Returns the list of created ``workflow_run`` IDs.
        """
        now = datetime.now(UTC)
        due_triggers = await self._schedule_repo.get_due_triggers(conn, now)

        created_run_ids: list[uuid.UUID] = []

        for trigger in due_triggers:
            try:
                run_id = await self._fire_trigger(conn, trigger, now)
                created_run_ids.append(run_id)
            except Exception:
                logger.exception(
                    "Failed to fire schedule trigger %s",
                    trigger["id"],
                )

        return created_run_ids

    async def run_loop(self, conn: AsyncConnection) -> None:
        """Run the polling loop until shutdown is requested.

        Calls :meth:`poll_once` every ``poll_interval`` seconds. Exceptions
        from individual polls are logged and swallowed so the loop continues.
        """
        while not self._shutdown_event.is_set():
            try:
                run_ids = await self.poll_once(conn)
                if run_ids:
                    logger.info("Scheduler created %d run(s): %s", len(run_ids), run_ids)
            except Exception:
                logger.exception("Scheduler poll error")
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=self.poll_interval
                )
                break  # Event was set, shutdown requested
            except TimeoutError:
                pass  # Normal timeout, continue polling

    def shutdown(self) -> None:
        """Signal the poller to stop after the current poll completes."""
        logger.info("Scheduler shutdown requested")
        self._shutdown_event.set()

    # ---- internal --------------------------------------------------------- #

    async def _fire_trigger(
        self,
        conn: AsyncConnection,
        trigger: dict[str, Any],
        now: datetime,
    ) -> uuid.UUID:
        """Create a workflow run for a single due trigger and advance next_fire_at."""
        workflow_id: uuid.UUID = trigger["workflow_id"]

        # Resolve published version, fall back to latest
        version = await self._version_repo.get_published(conn, workflow_id)
        if version is None:
            version = await self._version_repo.get_latest(conn, workflow_id)
        if version is None:
            raise ValueError(f"No workflow version found for workflow {workflow_id}")

        # Create workflow run
        run = await self._run_repo.create(
            conn,
            workflow_id=workflow_id,
            workflow_version_id=version["id"],
            inputs=trigger.get("inputs"),
            trigger_type="schedule",
            trigger_id=trigger["id"],
        )

        # Compute and persist the next fire time
        next_fire = compute_next_fire(
            trigger["cron_expression"],
            trigger.get("timezone", "UTC"),
            now,
        )
        await self._schedule_repo.update_after_fire(
            conn,
            trigger["id"],
            last_fired_at=now,
            next_fire_at=next_fire,
        )

        run_id: uuid.UUID = run["id"]
        return run_id
