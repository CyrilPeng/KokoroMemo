"""WebSocket endpoint for real-time push notifications."""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.events import subscribe, unsubscribe

logger = logging.getLogger("kokoromemo.ws")
router = APIRouter()

_active_connections: list[WebSocket] = []


def _websocket_authorized(websocket: WebSocket) -> bool:
    from app.api.routes_admin import _is_loopback
    from app.core.state import get_config

    cfg = get_config()
    token = cfg.server.get_admin_token()
    client_host = websocket.client.host if websocket.client else None
    if not token:
        return _is_loopback(client_host) or cfg.server.allow_remote_access
    auth = websocket.headers.get("authorization", "")
    if auth == f"Bearer {token}":
        return True
    return websocket.query_params.get("token", "") == token


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event push."""
    if not _websocket_authorized(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
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
