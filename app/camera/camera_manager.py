"""Manages all camera workers and distributes frames."""

from __future__ import annotations

import asyncio
import logging
import time
from threading import Lock
from typing import Callable, Optional

import cv2
import numpy as np

from app.camera.camera_worker import CameraWorker
from app.services.app_runtime import get_saved_camera_sources, load_ui_settings

LOGGER = logging.getLogger("anpr_new_gui.camera.manager")


class CameraManager:
    """Coordinates all camera workers and routes frames to consumers."""

    def __init__(self):
        self._workers: dict[int, CameraWorker] = {}
        self._latest_frames: dict[int, np.ndarray] = {}
        self._frame_callbacks: list[Callable[[int, np.ndarray], None]] = []
        self._lock = Lock()
        self._stream_quality = 60  # JPEG quality for WebSocket streaming
        self._stream_width = 640   # Downsample width for streaming

    def add_frame_callback(self, callback: Callable[[int, np.ndarray], None]) -> None:
        self._frame_callbacks.append(callback)

    def start_camera(
        self,
        camera_id: int,
        source: int | str,
        label: str = "",
        fps: int = 30,
    ) -> None:
        with self._lock:
            if camera_id in self._workers:
                return
        worker = CameraWorker(
            camera_index=camera_id,
            fps=fps,
            source=source,
            display_name=label or f"Camera {camera_id}",
            on_frame=self._on_frame,
            on_error=self._on_error,
        )
        with self._lock:
            self._workers[camera_id] = worker
        worker.start()
        LOGGER.info("Started camera %d (%s)", camera_id, label)

    def stop_camera(self, camera_id: int) -> None:
        with self._lock:
            worker = self._workers.pop(camera_id, None)
        if worker:
            worker.stop()
            LOGGER.info("Stopped camera %d", camera_id)

    def stop_all(self) -> None:
        with self._lock:
            workers = list(self._workers.items())
            self._workers.clear()
        for camera_id, worker in workers:
            worker.stop()
        LOGGER.info("All cameras stopped")

    def start_from_settings(self) -> None:
        sources = get_saved_camera_sources()
        for src in sources:
            self.start_camera(
                camera_id=src["camera_id"],
                source=src["source"],
                label=src["label"],
            )

    def get_latest_frame(self, camera_id: int) -> Optional[np.ndarray]:
        return self._latest_frames.get(camera_id)

    def encode_frame_jpeg(self, camera_id: int) -> Optional[bytes]:
        """Get latest frame as JPEG bytes for WebSocket streaming."""
        frame = self._latest_frames.get(camera_id)
        if frame is None:
            return None
        # Downsample for streaming
        h, w = frame.shape[:2]
        if w > self._stream_width:
            scale = self._stream_width / w
            frame = cv2.resize(
                frame,
                (self._stream_width, int(h * scale)),
                interpolation=cv2.INTER_LINEAR,
            )
        success, buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._stream_quality]
        )
        return buf.tobytes() if success else None

    @property
    def active_cameras(self) -> list[int]:
        with self._lock:
            return list(self._workers.keys())

    def _on_frame(self, camera_id: int, frame: np.ndarray) -> None:
        self._latest_frames[camera_id] = frame
        for callback in self._frame_callbacks:
            try:
                callback(camera_id, frame)
            except Exception as exc:
                LOGGER.error("Frame callback error: %s", exc)

    def _on_error(self, camera_id: int, message: str) -> None:
        LOGGER.error("Camera %d error: %s", camera_id, message)
        with self._lock:
            self._workers.pop(camera_id, None)
