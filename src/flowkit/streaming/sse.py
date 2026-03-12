"""SSE (Server-Sent Events) streaming helpers.

Provides an async generator that yields events for a workflow run, and a
formatter that converts event dicts to the SSE wire format.

Two delivery modes:
  1. **Redis pub/sub** (preferred) — subscribes to the run's channel and
     yields events in real time.
  2. **DB polling** (fallback) — queries the run_events table every second.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncConnection

    from flowkit.persistence.repos import RunEventRepo

logger = logging.getLogger(__name__)


def format_sse_event(event: dict[str, Any]) -> str:
    """Format an event dict as an SSE text block.

    Expected keys: ``id``, ``event``, ``data``.
    Returns a string like::

        id: 3
        event: node_started
        data: {"node_id": "n1"}

    (with a trailing double-newline to delimit the message).
    """
    data = event.get("data", "")
    if not isinstance(data, str):
        data = json.dumps(data, default=str)
    lines = [
        f"id: {event['id']}",
        f"event: {event['event']}",
        f"data: {data}",
    ]
    return "\n".join(lines) + "\n\n"


async def sse_event_stream(
    run_id: uuid.UUID,
    event_repo: RunEventRepo,
    conn: AsyncConnection,
    redis_client: Any | None = None,
    last_event_id: int | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield SSE-ready event dicts for *run_id*.

    Each yielded dict has: ``{"id": <sequence>, "event": <event_type>, "data": <json_payload>}``.
    """
    if redis_client is not None:
        async for event in _stream_via_redis(run_id, event_repo, conn, redis_client, last_event_id):
            yield event
    else:
        async for event in _stream_via_polling(run_id, event_repo, conn, last_event_id):
            yield event


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _row_to_sse(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a RunEventRepo row dict to an SSE-ready dict."""
    return {
        "id": row["sequence"],
        "event": row["event_type"],
        "data": json.dumps(row.get("payload") or {}, default=str),
    }


async def _stream_via_redis(
    run_id: uuid.UUID,
    event_repo: RunEventRepo,
    conn: AsyncConnection,
    redis_client: Any,
    last_event_id: int | None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Subscribe to Redis pub/sub and yield events."""
    # First, backfill any events the client missed
    after = last_event_id if last_event_id is not None else 0
    missed = await event_repo.list_by_run(conn, run_id, after_sequence=after)
    for row in missed:
        yield _row_to_sse(row)
        after = row["sequence"]

    # Subscribe to the real-time channel
    channel = f"flowkit:run:{run_id}:events"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            yield {
                "id": data["id"],
                "event": data["event"],
                "data": json.dumps(data.get("payload") or {}, default=str),
            }
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


async def _stream_via_polling(
    run_id: uuid.UUID,
    event_repo: RunEventRepo,
    conn: AsyncConnection,
    last_event_id: int | None,
    poll_interval: float = 1.0,
) -> AsyncGenerator[dict[str, Any], None]:
    """Poll the DB for new events every *poll_interval* seconds."""
    after = last_event_id if last_event_id is not None else 0
    while True:
        rows = await event_repo.list_by_run(conn, run_id, after_sequence=after)
        for row in rows:
            yield _row_to_sse(row)
            after = row["sequence"]
        await asyncio.sleep(poll_interval)
