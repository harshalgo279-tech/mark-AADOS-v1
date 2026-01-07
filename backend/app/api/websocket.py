# backend/app/api/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, Dict, Any
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"🔌 WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)
        logger.info(f"🔌 WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        if not self.active_connections:
            return

        disconnected: Set[WebSocket] = set()
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"❌ Error broadcasting to client: {str(e)}")
                disconnected.add(connection)

        for conn in disconnected:
            self.active_connections.discard(conn)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "message": "WebSocket connected successfully",
            "timestamp": datetime.now().isoformat()
        })

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"❌ WebSocket error: {str(e)}")
        manager.disconnect(websocket)


async def broadcast_activity(data: dict):
    message = {**data, "timestamp": datetime.now().isoformat()}
    await manager.broadcast(message)

async def broadcast_lead_update(lead_data: dict):
    await broadcast_activity({"type": "lead_update", "data": lead_data})

async def broadcast_call_update(call_data: dict):
    await broadcast_activity({"type": "call_update", "data": call_data})

async def broadcast_data_packet(packet_data: dict):
    await broadcast_activity({"type": "data_packet", "data": packet_data})

async def broadcast_transcript(transcript_data: dict):
    await broadcast_activity({"type": "transcript", "data": transcript_data})

async def broadcast_email(email_data: dict):
    await broadcast_activity({"type": "email", "data": email_data})

def get_connection_count() -> int:
    return len(manager.active_connections)
