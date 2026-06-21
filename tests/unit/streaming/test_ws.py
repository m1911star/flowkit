"""Tests for WebSocket streaming module."""

from __future__ import annotations

import uuid

import pytest
from starlette.testclient import TestClient

from flowkit.api.app import create_app
from flowkit.streaming.ws import ConnectionManager


class TestConnectionManager:
    """Unit tests for ConnectionManager."""

    @pytest.fixture()
    def mgr(self) -> ConnectionManager:
        return ConnectionManager()

    def test_connection_manager_connect_disconnect(self, mgr: ConnectionManager) -> None:
        """Connect and disconnect update internal state correctly."""
        run_id = uuid.uuid4()
        app = create_app()
        client = TestClient(app)

        # Use the endpoint to exercise connect; verify via get_connection_count
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            # Manager singleton gets the connection
            from flowkit.streaming.ws import manager

            assert manager.get_connection_count(run_id) >= 1
            ws.send_json({"action": "ping"})
            ws.receive_json()

        # After disconnect, count should be 0
        assert manager.get_connection_count(run_id) == 0

    @pytest.mark.asyncio()
    async def test_connection_manager_broadcast(self, mgr: ConnectionManager) -> None:
        """Broadcast sends messages to all connected WebSockets for a run."""
        run_id = uuid.uuid4()
        app = create_app()
        client = TestClient(app)

        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            from flowkit.streaming.ws import manager

            # Broadcast a message
            await manager.broadcast(run_id, {"type": "node_started", "node_id": "n1"})
            data = ws.receive_json()
            assert data == {"type": "node_started", "node_id": "n1"}


class TestWSEndpoint:
    """Integration tests for the /ws/runs/{run_id} endpoint."""

    @pytest.fixture()
    def client(self) -> TestClient:
        app = create_app()
        return TestClient(app)

    def test_ws_ping_pong(self, client: TestClient) -> None:
        """Ping action returns pong."""
        run_id = uuid.uuid4()
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            ws.send_json({"action": "ping"})
            data = ws.receive_json()
            assert data == {"type": "pong"}

    def test_ws_cancel_ack(self, client: TestClient) -> None:
        """Cancel action returns acknowledgement."""
        run_id = uuid.uuid4()
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            ws.send_json({"action": "cancel"})
            data = ws.receive_json()
            assert data == {"type": "ack", "action": "cancel", "run_id": str(run_id)}

    def test_ws_resume_ack(self, client: TestClient) -> None:
        """Resume action returns acknowledgement."""
        run_id = uuid.uuid4()
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            ws.send_json({"action": "resume"})
            data = ws.receive_json()
            assert data == {"type": "ack", "action": "resume", "run_id": str(run_id)}

    def test_ws_unknown_action(self, client: TestClient) -> None:
        """Unknown action returns error message."""
        run_id = uuid.uuid4()
        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            ws.send_json({"action": "foo"})
            data = ws.receive_json()
            assert data == {"type": "error", "message": "Unknown action: foo"}
