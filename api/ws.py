import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


class ConnectionManager:
    """Tracks all connected WebSocket clients and broadcasts to them."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        """Send state to every connected browser. Remove dead connections."""
        message = json.dumps(data)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


# Single global instance - imported by player.py to broadcast state changes
manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep the connection alive. We don't need to read from clients
            # but recv() is what keeps the loop running.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
