"""WebSocket endpoint for browser-fed detection and live share sessions."""

from __future__ import annotations

import asyncio
import logging
import struct
import uuid

import numpy as np
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.server.auth import decode_token
from app.server.websocket_manager import manager

LOGGER = logging.getLogger("anpr_new_gui.server.ws.feed")
router = APIRouter()


@router.websocket("/ws/feed")
async def feed_websocket(ws: WebSocket, token: str = Query(default="")):
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

    from app.server.main_server import get_detection_manager

    dm = get_detection_manager()
    loop = asyncio.get_running_loop()
    username = payload.get("username", "anon")
    user_id = int(payload["sub"]) if payload.get("sub") else None

    try:
        while True:
            message = await ws.receive()

            if "bytes" in message and message["bytes"]:
                raw = message["bytes"]
                if len(raw) < 4:
                    continue
                camera_id = struct.unpack(">I", raw[:4])[0]
                jpeg_bytes = raw[4:]
                LOGGER.info(
                    "Frame received from client conn=%s camera_id=%s bytes=%s",
                    conn_id,
                    camera_id,
                    len(jpeg_bytes),
                )

                if dm:
                    import cv2

                    buf = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        LOGGER.info(
                            "Submitting frame to detection pipeline conn=%s camera_id=%s event=detection",
                            conn_id,
                            camera_id,
                        )
                        dm.submit_frame_from_client(camera_id, frame, conn_id)

                    socket_event = dm.get_share_event(camera_id)
                    if socket_event:
                        LOGGER.info(
                            "Broadcasting shared frame conn=%s camera_id=%s socket_event=%s bytes=%s",
                            conn_id,
                            camera_id,
                            socket_event,
                            len(jpeg_bytes),
                        )
                        await manager.broadcast_shared_frame(socket_event, jpeg_bytes)
                continue

            if "text" not in message or not message["text"]:
                continue

            import json

            try:
                data = json.loads(message["text"])
            except Exception:
                continue

            msg_type = data.get("type", "")
            LOGGER.info("Control message received conn=%s type=%s payload=%s", conn_id, msg_type, data)

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})

            elif msg_type == "subscribe_camera":
                camera_id = int(data.get("camera_id", 0))
                await manager.subscribe(conn_id, camera_id)
                await ws.send_json(
                    {"type": "status", "camera_id": camera_id, "message": f"Subscribed to Camera {camera_id}"}
                )

            elif msg_type == "unsubscribe_camera":
                camera_id = int(data.get("camera_id", 0))
                await manager.unsubscribe(conn_id, camera_id)
                await ws.send_json(
                    {"type": "status", "camera_id": camera_id, "message": f"Unsubscribed from Camera {camera_id}"}
                )

            elif msg_type == "subscribe_share":
                socket_event = str(data.get("socket_event", "")).strip()
                if socket_event:
                    await manager.subscribe_share(conn_id, socket_event)
                    await ws.send_json(
                        {"type": "share_status", "socket_event": socket_event, "message": "Joined shared feed"}
                    )

            elif msg_type == "unsubscribe_share":
                socket_event = str(data.get("socket_event", "")).strip()
                if socket_event:
                    await manager.unsubscribe_share(conn_id, socket_event)
                    await ws.send_json(
                        {"type": "share_status", "socket_event": socket_event, "message": "Left shared feed"}
                    )

            elif msg_type == "start_detection":
                camera_id = int(data.get("camera_id", 0))
                label = str(data.get("label", f"CAM {camera_id}"))
                await manager.subscribe(conn_id, camera_id)
                if dm:
                    dm.start_client_camera(camera_id, label, conn_id, loop, share=False)
                await ws.send_json(
                    {"type": "status", "camera_id": camera_id, "message": "Detection started"}
                )

            elif msg_type == "stop_detection":
                camera_id = int(data.get("camera_id", 0))
                if dm:
                    dm.stop_client_camera(camera_id, conn_id)
                await ws.send_json(
                    {"type": "status", "camera_id": camera_id, "message": "Detection stopped"}
                )

            elif msg_type == "pause_detection":
                camera_id = int(data.get("camera_id", 0))
                if dm:
                    dm.pause_client_camera(camera_id, conn_id)
                await ws.send_json(
                    {"type": "status", "camera_id": camera_id, "message": "Detection paused"}
                )

            elif msg_type == "start_share":
                camera_id = int(data.get("camera_id", 0))
                label = str(data.get("label", f"CAM {camera_id}"))
                if not dm:
                    await ws.send_json({"type": "share_status", "message": "Share service unavailable"})
                    continue
                session = dm.start_share_session(
                    camera_id=camera_id,
                    label=label,
                    conn_id=conn_id,
                    owner_username=username,
                    owner_user_id=user_id,
                )
                if session:
                    await manager.subscribe_share(conn_id, session["socket_event"])
                    await ws.send_json(
                        {"type": "share_started", "session": session, "message": "Live feed sharing enabled"}
                    )
                else:
                    await ws.send_json({"type": "share_status", "message": "Unable to start sharing"})

            elif msg_type == "stop_share":
                camera_id = int(data.get("camera_id", 0))
                socket_event = str(data.get("socket_event", "")).strip()
                if dm and dm.stop_share_session(camera_id=camera_id, conn_id=conn_id):
                    if socket_event:
                        await manager.unsubscribe_share(conn_id, socket_event)
                    await ws.send_json(
                        {"type": "share_stopped", "camera_id": camera_id, "socket_event": socket_event}
                    )
                else:
                    await ws.send_json({"type": "share_status", "message": "Unable to stop sharing"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        LOGGER.error("WebSocket error for %s: %s", conn_id, exc)
    finally:
        if dm:
            dm.remove_client(conn_id)
        await manager.disconnect(conn_id)
        LOGGER.info("WebSocket disconnected: %s", conn_id)
