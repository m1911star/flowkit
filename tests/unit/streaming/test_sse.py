"""Tests for flowkit.streaming.sse — SSE helpers."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from flowkit.persistence.repos import RunEventRepo
from flowkit.streaming.emitter import NODE_COMPLETED, NODE_STARTED, RUN_STARTED, EventEmitter
from flowkit.streaming.sse import format_sse_event, sse_event_stream

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

# --------------------------------------------------------------------------- #
# format_sse_event
# --------------------------------------------------------------------------- #


class TestFormatSseEvent:
    """Tests for the SSE text formatter."""

    def test_basic_format(self) -> None:
        event = {
            "id": 1,
            "event": "run_started",
            "data": '{"inputs": {}}',
        }
        result = format_sse_event(event)
        assert result == 'id: 1\nevent: run_started\ndata: {"inputs": {}}\n\n'

    def test_format_with_dict_data(self) -> None:
        """When data is a dict instead of string, it should be JSON-serialized."""
        event = {
            "id": 5,
            "event": "node_completed",
            "data": {"outputs": {"result": 42}},
        }
        result = format_sse_event(event)
        assert "id: 5\n" in result
        assert "event: node_completed\n" in result
        assert "data: " in result
        # Verify the data was JSON-encoded
        data_line = [line for line in result.split("\n") if line.startswith("data:")][0]
        data_json = data_line[len("data: ") :]
        parsed = json.loads(data_json)
        assert parsed == {"outputs": {"result": 42}}

    def test_format_ends_with_double_newline(self) -> None:
        event = {"id": 1, "event": "test", "data": "{}"}
        result = format_sse_event(event)
        assert result.endswith("\n\n")

    def test_format_empty_data(self) -> None:
        event = {"id": 3, "event": "run_paused", "data": ""}
        result = format_sse_event(event)
        assert "data: \n" in result


# --------------------------------------------------------------------------- #
# sse_event_stream — polling fallback
# --------------------------------------------------------------------------- #


class TestSseEventStreamPolling:
    """Test the DB-polling fallback path of sse_event_stream."""

    async def test_polling_yields_events(self, conn: AsyncConnection) -> None:
        """Insert events then verify the stream yields them."""
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo)
        run_id = uuid.uuid4()

        # Pre-create some events
        await emitter.emit(conn, run_id, RUN_STARTED, payload={"inputs": {}})
        await emitter.emit(conn, run_id, NODE_STARTED, node_id="n1")
        await emitter.emit(conn, run_id, NODE_COMPLETED, node_id="n1")

        # Collect events from the stream (no redis → polling mode)
        collected: list[dict] = []
        gen = sse_event_stream(run_id, repo, conn, redis_client=None, last_event_id=None)

        # The polling loop is infinite, so we take what we need and break
        async for event in gen:
            collected.append(event)
            if len(collected) >= 3:
                break

        assert len(collected) == 3
        assert collected[0]["id"] == 1
        assert collected[0]["event"] == "run_started"
        assert collected[1]["id"] == 2
        assert collected[1]["event"] == "node_started"
        assert collected[2]["id"] == 3
        assert collected[2]["event"] == "node_completed"

    async def test_polling_respects_last_event_id(self, conn: AsyncConnection) -> None:
        """Events before last_event_id should be skipped."""
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo)
        run_id = uuid.uuid4()

        await emitter.emit(conn, run_id, RUN_STARTED)
        await emitter.emit(conn, run_id, NODE_STARTED, node_id="n1")
        await emitter.emit(conn, run_id, NODE_COMPLETED, node_id="n1")

        collected: list[dict] = []
        gen = sse_event_stream(run_id, repo, conn, redis_client=None, last_event_id=2)

        async for event in gen:
            collected.append(event)
            if len(collected) >= 1:
                break

        assert len(collected) == 1
        assert collected[0]["id"] == 3

    async def test_each_event_has_sse_keys(self, conn: AsyncConnection) -> None:
        """Verify each yielded event has the expected SSE dict shape."""
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo)
        run_id = uuid.uuid4()

        await emitter.emit(conn, run_id, RUN_STARTED, payload={"k": "v"})

        gen = sse_event_stream(run_id, repo, conn, redis_client=None)
        async for event in gen:
            assert "id" in event
            assert "event" in event
            assert "data" in event
            break
