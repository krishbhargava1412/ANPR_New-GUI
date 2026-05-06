"""WebSocket endpoint — receives frames from the JS frontend, runs detection, emits results."""

from __future__ import annotations

import asyncio
import logging
import struct
import uuid

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.server.auth import decode_token
from app.server.websocket_manager import manager

LOGGER = logging.getLogger("anpr_new_gui.server.ws.feed")
router = APIRouter()


@router.websocket("/ws/feed")
async def feed_websocket(ws: WebSocket, token: str = Query(default="")):
    """Main WebSocket endpoint.

    Message protocol (client → server):
      - JSON  {"type": "ping"}
      - JSON  {"type": "start_detection", "camera_id": <int>, "label": <str>}
      - JSON  {"type": "stop_detection",  "camera_id": <int>}
      - JSON  {"type": "pause_detection", "camera_id": <int>}
      - Binary [4-byte big-endian camera_id] + [JPEG bytes]   ← camera frame from browser

    Message protocol (server → client):
      - JSON  {"type": "detection", ...}
      - JSON  {"type": "telemetry", ...}
      - JSON  {"type": "status",    "camera_id": ..., "message": ...}
      - JSON  {"type": "alert",     ...}
    """
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return
    try:
        payload = decode_token(token)
    except Exception:
        await ws.close(code=4001, reason="Invalid token")
        return

    conn_id = f"{payload.get('username', 'anon')}_{uuid.uuid4().hex[:8]}"
    await manager.connect(ws, conn_id)
    LOGGER.info("WebSocket connected: %s", conn_id)

    # Import the detection manager (set up in lifespan)
    from app.server.main_server import get_detection_manager
    dm = get_detection_manager()

    loop = asyncio.get_running_loop()

    try:
        while True:
            message = await ws.receive()

            # ── Binary frame from browser camera ──────────────────────────────
            if "bytes" in message and message["bytes"]:
                raw = message["bytes"]
                if len(raw) < 4:
                    continue
                camera_id = struct.unpack(">I", raw[:4])[0]
                jpeg_bytes = raw[4:]
                
                LOGGER.info("Frame received: ConnID=%s, CamID=%d, Size=%.1f KB", conn_id, camera_id, len(raw) / 1024.0)

                # Decode JPEG → numpy for the detection pipeline
                if dm:
                    import cv2
                    buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        dm.submit_frame_from_client(camera_id, frame, conn_id)

                # Broadcast the frame only if the source has opted into sharing
                if dm and dm.is_camera_shared(camera_id):
                    await manager.broadcast_frame(camera_id, jpeg_bytes)
                
                continue

            # ── JSON control messages ─────────────────────────────────────────
            if "text" in message and message["text"]:
                import json
                try:
                    data = json.loads(message["text"])
                except Exception:
                    continue

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})

                elif msg_type == "subscribe_camera":
                    camera_id = int(data.get("camera_id", 0))
                    await manager.subscribe(conn_id, camera_id)
                    await ws.send_json({"type": "status", "camera_id": camera_id, "message": f"Subscribed to Camera {camera_id}"})

                elif msg_type == "unsubscribe_camera":
                    camera_id = int(data.get("camera_id", 0))
                    await manager.unsubscribe(conn_id, camera_id)
                    await ws.send_json({"type": "status", "camera_id": camera_id, "message": f"Unsubscribed from Camera {camera_id}"})

                elif msg_type == "start_detection":
                    camera_id = int(data.get("camera_id", 0))
                    label = str(data.get("label", f"CAM {camera_id}"))
                    share = bool(data.get("share", False))
                    # Auto-subscribe the person who starts the detection
                    await manager.subscribe(conn_id, camera_id)
                    if dm:
                        dm.start_client_camera(camera_id, label, conn_id, loop, share=share)
                    await ws.send_json({"type": "status", "camera_id": camera_id, "message": "Detection started"})

                elif msg_type == "stop_detection":
                    camera_id = int(data.get("camera_id", 0))
                    if dm:
                        dm.stop_client_camera(camera_id, conn_id)
                    await ws.send_json({"type": "status", "camera_id": camera_id, "message": "Detection stopped"})

                elif msg_type == "pause_detection":
                    camera_id = int(data.get("camera_id", 0))
                    if dm:
                        dm.pause_client_camera(camera_id, conn_id)
                    await ws.send_json({"type": "status", "camera_id": camera_id, "message": "Detection paused"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        LOGGER.error("WebSocket error for %s: %s", conn_id, exc)
    finally:
        if dm:
            dm.remove_client(conn_id)
        await manager.disconnect(conn_id)
        LOGGER.info("WebSocket disconnected: %s", conn_id)
