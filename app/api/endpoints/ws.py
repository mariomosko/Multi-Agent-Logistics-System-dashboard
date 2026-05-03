"""
WebSocket endpoint — /api/v1/ws

Dashboard clients connect here to receive a stream of real-time pipeline
events (agent.started, agent.completed, pipeline.resolved, etc.).

Each connected client stays open until it disconnects or the server shuts
down. The endpoint deliberately accepts all origins; add an Origin check
here if you need to restrict access in production.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.websocket_manager import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        # Block until the client disconnects.
        # We don't expect messages from the client; receive_text() is just
        # a convenient way to detect a closed connection.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
