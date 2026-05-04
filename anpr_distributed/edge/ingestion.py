"""
Camera ingestion service for the Jetson edge node.

Replaces CameraWorker(QThread) with a pure-Python threaded approach.
No PyQt6 dependency — runs headless.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Callable, Optional

import cv2
import numpy as np

from edge.config import FRAME_SKIP, NORMAL_FPS, THERMAL_THROTTLE_FPS

LOGGER = logging.getLogger("anpr.edge.ingestion")


class CameraStream:
    """Manages a single camera RTSP/USB stream in a dedicated thread."""

    _CONSECUTIVE_FAIL_LIMIT = 10
    _RECONNECT_DELAY = 5.0

    def __init__(
        self,
        camera_id: str,
        source: int | str,
        label: str = "",
        fps: int = NORMAL_FPS,
    ):
        self.camera_id = camera_id
        self.source = source
        self.label = label or camera_id
        self._target_fps = fps
        self._current_fps = fps
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Latest frame (overwritten each capture — no queuing)
        self._frame: Optional[np.ndarray] = None
        self._frame_id: int = 0
        self._last_read_frame_id: int = -1

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, name=f"cam-{self.camera_id}", daemon=True
        )
        self._thread.start()
        LOGGER.info("Camera '%s' stream started (source=%s).", self.label, self.source)

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        LOGGER.info("Camera '%s' stream stopped.", self.label)

    def get_frame(self) -> Optional[tuple[np.ndarray, int]]:
        """Get the latest frame if a new one is available. Returns (frame, frame_id) or None."""
        with self._lock:
            if self._frame is None or self._frame_id == self._last_read_frame_id:
                return None
            self._last_read_frame_id = self._frame_id
            return self._frame.copy(), self._frame_id

    def set_fps(self, fps: int) -> None:
        """Dynamically adjust FPS (used by thermal throttling)."""
        with self._lock:
            self._current_fps = max(1, fps)

    def _capture_loop(self) -> None:
        """Main capture loop — runs in a dedicated thread."""
        while True:
            with self._lock:
                if not self._running:
                    return

            cap = self._open_capture()
            if not cap.isOpened():
                LOGGER.error("Cannot open camera '%s' (source=%s). Retrying in %.0fs...",
                             self.label, self.source, self._RECONNECT_DELAY)
                time.sleep(self._RECONNECT_DELAY)
                continue

            LOGGER.info("Camera '%s' connected.", self.label)
            consecutive_failures = 0
            frame_count = 0

            while True:
                with self._lock:
                    if not self._running:
                        cap.release()
                        return
                    fps = self._current_fps

                ret, frame = cap.read()

                if not ret:
                    consecutive_failures += 1
                    if consecutive_failures >= self._CONSECUTIVE_FAIL_LIMIT:
                        LOGGER.warning(
                            "Camera '%s' failed %d reads. Reconnecting...",
                            self.label, consecutive_failures,
                        )
                        break
                    time.sleep(1.0 / fps)
                    continue

                consecutive_failures = 0
                frame_count += 1

                # Frame skip — only process every Nth frame
                if frame_count % FRAME_SKIP != 0:
                    time.sleep(1.0 / fps)
                    continue

                # Store latest frame
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1

                time.sleep(1.0 / fps)

            cap.release()
            LOGGER.info("Camera '%s' disconnected. Reconnecting in %.0fs...",
                         self.label, self._RECONNECT_DELAY)
            time.sleep(self._RECONNECT_DELAY)

    def _open_capture(self) -> cv2.VideoCapture:
        if isinstance(self.source, int):
            return cv2.VideoCapture(self.source, cv2.CAP_ANY)
        # For RTSP, prefer GStreamer with hardware decoding on Jetson
        gst_pipeline = (
            f"rtspsrc location={self.source} latency=100 ! "
            f"rtph264depay ! h264parse ! nvv4l2decoder ! "
            f"nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! "
            f"video/x-raw,format=BGR ! appsink drop=1"
        )
        cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            LOGGER.info("Opened '%s' with GStreamer HW decoder.", self.label)
            return cap
        # Fallback to standard OpenCV
        LOGGER.info("GStreamer unavailable for '%s', using OpenCV fallback.", self.label)
        return cv2.VideoCapture(str(self.source))


class IngestionManager:
    """Manages multiple camera streams."""

    def __init__(self, camera_configs: list[dict]):
        self.streams: dict[str, CameraStream] = {}
        for cfg in camera_configs:
            stream = CameraStream(
                camera_id=cfg["id"],
                source=cfg["source"],
                label=cfg.get("label", cfg["id"]),
            )
            self.streams[cfg["id"]] = stream

    def start_all(self) -> None:
        for stream in self.streams.values():
            stream.start()

    def stop_all(self) -> None:
        for stream in self.streams.values():
            stream.stop()

    def get_latest_frames(self) -> dict[str, tuple[np.ndarray, int]]:
        """Collect latest frames from all cameras that have new data."""
        frames = {}
        for cam_id, stream in self.streams.items():
            result = stream.get_frame()
            if result is not None:
                frames[cam_id] = result
        return frames

    def set_all_fps(self, fps: int) -> None:
        """Throttle all cameras to a given FPS."""
        for stream in self.streams.values():
            stream.set_fps(fps)
