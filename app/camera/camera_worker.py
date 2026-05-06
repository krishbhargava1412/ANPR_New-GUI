"""Camera capture worker — stdlib threading version (replaces QThread)."""

from __future__ import annotations

import logging
import time
from threading import Lock, Thread
from typing import Callable, Optional

import cv2
import numpy as np

LOGGER = logging.getLogger("anpr_new_gui.camera")


class CameraWorker(Thread):
    """
    Captures frames from a single camera index in a dedicated thread.
    Calls on_frame(camera_index, numpy BGR frame) for each captured frame.
    Calls on_error(camera_index, message) if the camera fails.
    """

    _CONSECUTIVE_FAIL_LIMIT = 10

    def __init__(
        self,
        camera_index: int,
        fps: int = 30,
        *,
        source: int | str | None = None,
        display_name: str | None = None,
        on_frame: Optional[Callable[[int, np.ndarray], None]] = None,
        on_error: Optional[Callable[[int, str], None]] = None,
    ):
        super().__init__(daemon=True, name=f"CameraWorker-{camera_index}")
        self.camera_index = camera_index
        self.source = camera_index if source is None else source
        self.display_name = display_name or f"Camera {camera_index}"
        self._fps = max(1, fps)
        self._running = False
        self._lock = Lock()
        self._on_frame = on_frame
        self._on_error = on_error
        self._frame_count = 0

    def run(self):
        cap = self._open_capture()

        if not cap.isOpened():
            if self._on_error:
                self._on_error(self.camera_index, f"Cannot open {self.display_name}")
            return

        cap.set(cv2.CAP_PROP_FPS, self._fps)
        interval = 1.0 / self._fps
        consecutive_failures = 0

        with self._lock:
            self._running = True

        while True:
            with self._lock:
                if not self._running:
                    break

            ret, frame = cap.read()

            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= self._CONSECUTIVE_FAIL_LIMIT:
                    if self._on_error:
                        self._on_error(
                            self.camera_index,
                            f"{self.display_name} read failed {consecutive_failures} times",
                        )
                    break
                time.sleep(interval)
                continue

            consecutive_failures = 0
            self._frame_count += 1
            if self._frame_count % 30 == 0:
                LOGGER.info(f"[{self.display_name}] Backend successfully receiving frames (Total: {self._frame_count})")
                
            if self._on_frame:
                self._on_frame(self.camera_index, frame)
            time.sleep(interval)

        cap.release()

    def stop(self):
        with self._lock:
            self._running = False
        self.join(timeout=5)

    def _open_capture(self):
        if isinstance(self.source, int):
            return cv2.VideoCapture(self.source, cv2.CAP_ANY)
        return cv2.VideoCapture(str(self.source))
