"""WebSocket streaming — real-time bidirectional event transport."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uuid import UUID

    from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections per run_id."""

    def __init__(self) -> None:
        self._connections: dict[UUID, list[WebSocket]] = {}

    async def connect(self, run_id: UUID, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)
        logger.info(
            "WS connected for run %s (total: %d)", run_id, len(self._connections[run_id])
        )

    def disconnect(self, run_id: UUID, ws: WebSocket) -> None:
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(run_id, None)
        logger.info("WS disconnected for run %s", run_id)

    async def broadcast(self, run_id: UUID, message: dict[str, Any]) -> None:
        """Send a message to all connections watching this run."""
        conns = self._connections.get(run_id, [])
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)

    def get_connection_count(self, run_id: UUID) -> int:
        return len(self._connections.get(run_id, []))


# Module-level singleton
manager = ConnectionManager()
