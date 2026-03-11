"""Tests for flowkit.streaming.emitter — EventEmitter."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from flowkit.persistence.repos import RunEventRepo
from flowkit.streaming.emitter import (
    ALL_EVENT_TYPES,
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_RESUMED,
    NODE_STARTED,
    NODE_WAITING,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_PAUSED,
    RUN_RESUMED,
    RUN_STARTED,
    EventEmitter,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_run_id() -> uuid.UUID:
    return uuid.uuid4()


# --------------------------------------------------------------------------- #
# Tests with real DB (aiosqlite)
# --------------------------------------------------------------------------- #


class TestEmitterWithDB:
    """EventEmitter integration tests against a real (in-memory) DB."""

    async def test_emit_creates_event_with_correct_sequence(self, conn: AsyncConnection) -> None:
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo)
        run_id = _make_run_id()

        event = await emitter.emit(conn, run_id, RUN_STARTED, payload={"inputs": {"x": 1}})

        assert event["sequence"] == 1
        assert event["event_type"] == RUN_STARTED
        assert event["workflow_run_id"] == run_id
        assert event["payload"] == {"inputs": {"x": 1}}

    async def test_sequence_numbers_increment(self, conn: AsyncConnection) -> None:
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo)
        run_id = _make_run_id()

        e1 = await emitter.emit(conn, run_id, RUN_STARTED)
        e2 = await emitter.emit(conn, run_id, NODE_STARTED, node_id="n1")
        e3 = await emitter.emit(conn, run_id, NODE_COMPLETED, node_id="n1")

        assert e1["sequence"] == 1
        assert e2["sequence"] == 2
        assert e3["sequence"] == 3

    async def test_emit_stores_node_id(self, conn: AsyncConnection) -> None:
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo)
        run_id = _make_run_id()

        event = await emitter.emit(conn, run_id, NODE_STARTED, node_id="my_node")
        assert event["node_id"] == "my_node"

    async def test_emit_without_redis_succeeds(self, conn: AsyncConnection) -> None:
        """Emitter works fine without a Redis client (no-op for pub/sub)."""
        repo = RunEventRepo()
        emitter = EventEmitter(event_repo=repo, redis_client=None)
        run_id = _make_run_id()

        event = await emitter.emit(conn, run_id, RUN_COMPLETED)
        assert event["event_type"] == RUN_COMPLETED


class TestEmitterWithRedis:
    """EventEmitter tests verifying Redis pub/sub integration (mocked)."""

    async def test_emit_publishes_to_redis(self, conn: AsyncConnection) -> None:
        repo = RunEventRepo()
        redis_mock = AsyncMock()
        emitter = EventEmitter(event_repo=repo, redis_client=redis_mock)
        run_id = _make_run_id()

        await emitter.emit(conn, run_id, NODE_STARTED, node_id="n1", payload={"node_type": "http"})

        redis_mock.publish.assert_awaited_once()
        call_args = redis_mock.publish.call_args
        channel = call_args[0][0]
        message = json.loads(call_args[0][1])

        assert channel == f"flowkit:run:{run_id}:events"
        assert message["id"] == 1
        assert message["event"] == NODE_STARTED
        assert message["node_id"] == "n1"
        assert message["payload"] == {"node_type": "http"}

    async def test_emit_survives_redis_failure(self, conn: AsyncConnection) -> None:
        """If Redis publish fails, the event is still persisted in DB."""
        repo = RunEventRepo()
        redis_mock = AsyncMock()
        redis_mock.publish.side_effect = ConnectionError("Redis down")
        emitter = EventEmitter(event_repo=repo, redis_client=redis_mock)
        run_id = _make_run_id()

        # Should NOT raise
        event = await emitter.emit(conn, run_id, RUN_FAILED)
        assert event["event_type"] == RUN_FAILED
        assert event["sequence"] == 1

        # Verify event was persisted despite Redis failure
        events = await repo.list_by_run(conn, run_id)
        assert len(events) == 1


class TestEventTypeConstants:
    """Verify all 11 event type constants exist."""

    def test_all_event_types_count(self) -> None:
        assert len(ALL_EVENT_TYPES) == 11

    def test_event_type_values(self) -> None:
        expected = {
            "run_started",
            "run_completed",
            "run_failed",
            "run_paused",
            "run_resumed",
            "run_cancelled",
            "node_started",
            "node_completed",
            "node_failed",
            "node_waiting",
            "node_resumed",
        }
        assert ALL_EVENT_TYPES == expected
