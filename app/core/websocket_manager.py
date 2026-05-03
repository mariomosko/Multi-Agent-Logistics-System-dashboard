"""
WebSocket connection manager — singleton shared across the entire process.

All connected dashboard clients receive every broadcast. In a multi-worker
deployment you would replace this with a Redis pub/sub fan-out; for a
single-worker demo (uvicorn without --workers) this is sufficient.
"""
import json
import logging
from typing import Any

from fastapi import WebSocket

_log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        _log.info("WebSocket connected  total=%d", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        try:
            self._connections.remove(ws)
        except ValueError:
            pass
        _log.info("WebSocket disconnected  total=%d", len(self._connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Send JSON to every connected client; silently drop dead connections."""
        if not self._connections:
            return
        text = json.dumps(payload, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Process-wide singleton
manager = ConnectionManager()
