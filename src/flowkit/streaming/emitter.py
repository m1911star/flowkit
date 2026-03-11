"""Event emitter — writes events to DB and optionally publishes to Redis pub/sub.

The emitter is the single point of event creation for a workflow run.
It guarantees monotonic sequence numbers and persistent storage before
any real-time notification is sent.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.persistence.repos import RunEventRepo

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Event type constants
# --------------------------------------------------------------------------- #
RUN_STARTED = "run_started"
RUN_COMPLETED = "run_completed"
RUN_FAILED = "run_failed"
RUN_PAUSED = "run_paused"
RUN_RESUMED = "run_resumed"
RUN_CANCELLED = "run_cancelled"
NODE_STARTED = "node_started"
NODE_COMPLETED = "node_completed"
NODE_FAILED = "node_failed"
NODE_WAITING = "node_waiting"
NODE_RESUMED = "node_resumed"

ALL_EVENT_TYPES = frozenset(
    {
        RUN_STARTED,
        RUN_COMPLETED,
        RUN_FAILED,
        RUN_PAUSED,
        RUN_RESUMED,
        RUN_CANCELLED,
        NODE_STARTED,
        NODE_COMPLETED,
        NODE_FAILED,
        NODE_WAITING,
        NODE_RESUMED,
    }
)


# --------------------------------------------------------------------------- #
# EventEmitter
# --------------------------------------------------------------------------- #
class EventEmitter:
    """Emit workflow-run events to DB with optional Redis pub/sub fanout."""

    def __init__(
        self,
        event_repo: RunEventRepo,
        redis_client: Any | None = None,
    ) -> None:
        self._repo = event_repo
        self._redis = redis_client

    async def emit(
        self,
        conn: AsyncConnection,
        run_id: uuid.UUID,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an event, persist it, and optionally publish via Redis.

        Returns the created event dict (same shape as RunEventRepo.create).
        """
        # 1. Determine next sequence number
        latest_seq = await self._repo.get_latest_sequence(conn, run_id)
        next_seq = latest_seq + 1

        # 2. Persist to DB
        event = await self._repo.create(
            conn,
            workflow_run_id=run_id,
            sequence=next_seq,
            event_type=event_type,
            node_id=node_id,
            payload=payload,
        )

        # 3. Publish to Redis if available
        if self._redis is not None:
            channel = f"flowkit:run:{run_id}:events"
            message = json.dumps(
                {
                    "id": next_seq,
                    "event": event_type,
                    "node_id": node_id,
                    "payload": payload,
                },
                default=str,
            )
            try:
                await self._redis.publish(channel, message)
            except Exception:
                logger.warning(
                    "Failed to publish event to Redis channel %s",
                    channel,
                    exc_info=True,
                )

        return event
