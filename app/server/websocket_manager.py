"""WebSocket connection manager for real-time frame & event broadcast."""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import Any

from fastapi import WebSocket

LOGGER = logging.getLogger("anpr_new_gui.server.ws")


class ConnectionManager:
    """Tracks active WebSocket connections and camera subscriptions."""

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, set[int]] = {}  # conn_id → {camera_ids}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, conn_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[conn_id] = ws
            self._subscriptions[conn_id] = set()
        LOGGER.info("WebSocket connected: %s", conn_id)

    async def disconnect(self, conn_id: str) -> None:
        async with self._lock:
            self._connections.pop(conn_id, None)
            self._subscriptions.pop(conn_id, None)
        LOGGER.info("WebSocket disconnected: %s", conn_id)

    async def subscribe(self, conn_id: str, camera_id: int) -> None:
        async with self._lock:
            subs = self._subscriptions.get(conn_id)
            if subs is not None:
                subs.add(camera_id)

    async def unsubscribe(self, conn_id: str, camera_id: int) -> None:
        async with self._lock:
            subs = self._subscriptions.get(conn_id)
            if subs is not None:
                subs.discard(camera_id)

    async def broadcast_frame(self, camera_id: int, jpeg_bytes: bytes) -> None:
        """Send binary frame: [4 bytes camera_id big-endian] + [JPEG bytes]."""
        header = struct.pack(">I", camera_id)
        payload = header + jpeg_bytes
        async with self._lock:
            targets = [
                (cid, ws)
                for cid, ws in self._connections.items()
                if camera_id in self._subscriptions.get(cid, set())
            ]
        for conn_id, ws in targets:
            try:
                await ws.send_bytes(payload)
            except Exception:
                await self.disconnect(conn_id)

    async def broadcast_json(self, data: dict[str, Any], camera_id: int | None = None) -> None:
        """Send JSON event to all connections (or only those subscribed to camera_id)."""
        async with self._lock:
            if camera_id is not None:
                targets = [
                    (cid, ws)
                    for cid, ws in self._connections.items()
                    if camera_id in self._subscriptions.get(cid, set())
                ]
            else:
                targets = list(self._connections.items())
        for conn_id, ws in targets:
            try:
                await ws.send_json(data)
            except Exception:
                await self.disconnect(conn_id)

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()
