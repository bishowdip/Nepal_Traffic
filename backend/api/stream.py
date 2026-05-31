"""
WebSocket live feed endpoints.
/ws/live/{checkpoint_id}   - live vehicle sightings
/ws/alerts/{checkpoint_id} - live alert events
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Maps: checkpoint_id → set of connected WebSocket clients
_sighting_clients: Dict[str, Set[WebSocket]] = defaultdict(set)
_alert_clients:    Dict[str, Set[WebSocket]] = defaultdict(set)

PING_INTERVAL = 30  # seconds


async def _ping_loop(ws: WebSocket):
    """Keep WebSocket alive by sending pings every 30 seconds."""
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            await ws.send_text(json.dumps({"type": "ping"}))
    except Exception:
        pass


@router.websocket("/ws/live/{checkpoint_id}")
async def ws_live(websocket: WebSocket, checkpoint_id: str):
    await websocket.accept()
    _sighting_clients[checkpoint_id].add(websocket)
    logger.info(f"WS sighting client connected: checkpoint={checkpoint_id}")

    ping_task = asyncio.create_task(_ping_loop(websocket))

    try:
        while True:
            # Just listen for control messages (e.g. disconnect)
            data = await websocket.receive_text()
            # Could handle filter requests here
    except WebSocketDisconnect:
        logger.info(f"WS sighting client disconnected: checkpoint={checkpoint_id}")
    except Exception as e:
        logger.warning(f"WS sighting error: {e}")
    finally:
        ping_task.cancel()
        _sighting_clients[checkpoint_id].discard(websocket)


@router.websocket("/ws/alerts/{checkpoint_id}")
async def ws_alerts(websocket: WebSocket, checkpoint_id: str):
    await websocket.accept()
    _alert_clients[checkpoint_id].add(websocket)
    logger.info(f"WS alert client connected: checkpoint={checkpoint_id}")

    ping_task = asyncio.create_task(_ping_loop(websocket))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(f"WS alert client disconnected: checkpoint={checkpoint_id}")
    except Exception as e:
        logger.warning(f"WS alert error: {e}")
    finally:
        ping_task.cancel()
        _alert_clients[checkpoint_id].discard(websocket)


async def broadcast_sighting(checkpoint_id: str, data: dict):
    """Broadcast a new vehicle sighting to all connected clients."""
    payload = json.dumps({"type": "sighting", "data": data}, default=str)
    dead: Set[WebSocket] = set()
    for ws in list(_sighting_clients.get(checkpoint_id, set())):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _sighting_clients[checkpoint_id].discard(ws)


async def broadcast_alert(checkpoint_id: str, data: dict):
    """Broadcast an alert event to all connected clients."""
    payload = json.dumps({"type": "alert", "data": data}, default=str)
    dead: Set[WebSocket] = set()
    for ws in list(_alert_clients.get(checkpoint_id, set())):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _alert_clients[checkpoint_id].discard(ws)
