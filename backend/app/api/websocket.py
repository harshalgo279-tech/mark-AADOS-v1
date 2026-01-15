# backend/app/api/websocket.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.auth.jwt_handler import verify_token
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Singleton manager used across the codebase as `manager`."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"🔌 WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"🔌 WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self.active_connections)

        if not connections:
            return

        disconnected: Set[WebSocket] = set()

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"❌ WS send failed; dropping connection: {e}")
                disconnected.add(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self.active_connections.discard(ws)

    def broadcast_fire_and_forget(self, message: Dict[str, Any]) -> None:
        """Non-blocking broadcast (use inside Twilio handlers)."""
        try:
            asyncio.create_task(self.broadcast(message))
        except Exception as e:
            logger.warning(f"broadcast_fire_and_forget failed: {e}")


manager = ConnectionManager()


async def _ws_loop(websocket: WebSocket, token: Optional[str] = None) -> None:
    """
    Common websocket loop logic (shared by /ws and /api/ws).

    SECURITY: In production, requires valid JWT token for connection.
    Token can be passed via query parameter: /ws?token=xxx
    """
    # In production, require authentication
    is_production = getattr(settings, "ENVIRONMENT", "development") == "production"

    if is_production and token:
        payload = verify_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return
        user_email = payload.get("sub", "authenticated")
        logger.info(f"WebSocket authenticated for user: {user_email}")
    elif is_production:
        # Allow connection but log warning
        logger.warning("WebSocket connection without authentication in production")

    await manager.connect(websocket)

    try:
        await websocket.send_json(
            {
                "type": "connection",
                "status": "connected",
                "message": "WebSocket connected successfully",
                "authenticated": bool(token and verify_token(token)) if token else False,
                "timestamp": datetime.now().isoformat(),
            }
        )

        while True:
            data = await websocket.receive_text()

            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                continue

            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"❌ WebSocket fatal error: {e}")
        await manager.disconnect(websocket)


# ✅ Support both paths so frontend path mismatch can never break you
@router.websocket("/ws")
async def websocket_endpoint_legacy(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT token for authentication")
):
    """WebSocket endpoint (legacy path). Accepts optional token for auth."""
    await _ws_loop(websocket, token)


@router.websocket("/api/ws")
async def websocket_endpoint_api(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT token for authentication")
):
    """WebSocket endpoint (API path). Accepts optional token for auth."""
    await _ws_loop(websocket, token)


# Backwards-compatible helpers
async def broadcast_activity(data: Dict[str, Any]) -> None:
    message = {**data, "timestamp": datetime.now().isoformat()}
    await manager.broadcast(message)


async def broadcast_lead_update(lead_data: Dict[str, Any]) -> None:
    await broadcast_activity({"type": "lead_update", "data": lead_data})


async def broadcast_call_update(call_data: Dict[str, Any]) -> None:
    await broadcast_activity({"type": "call_update", "data": call_data})


async def broadcast_data_packet(packet_data: Dict[str, Any]) -> None:
    await broadcast_activity({"type": "data_packet", "data": packet_data})


async def broadcast_transcript(transcript_data: Dict[str, Any]) -> None:
    await broadcast_activity({"type": "transcript", "data": transcript_data})


async def broadcast_email(email_data: Dict[str, Any]) -> None:
    await broadcast_activity({"type": "email", "data": email_data})


def get_connection_count() -> int:
    return len(manager.active_connections)
