"""WebSocket endpoint for real-time push notifications."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import subscribe, unsubscribe

logger = logging.getLogger("kokoromemo.ws")
router = APIRouter()

_active_connections: list[WebSocket] = []


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event push."""
    await websocket.accept()
    _active_connections.append(websocket)

    async def _listener(event_type: str, payload: dict):
        try:
            await websocket.send_json({"event": event_type, **payload})
        except Exception:
            pass

    subscribe(_listener)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(_listener)
        try:
            _active_connections.remove(websocket)
        except ValueError:
            pass
