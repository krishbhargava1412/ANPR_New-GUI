import cv2
import numpy as np

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


class CameraWorker(QThread):
    """
    Captures frames from a single camera index in a dedicated thread.
    Emits frame_ready with (camera_index, numpy BGR frame).
    Emits error if the camera cannot be opened or read fails repeatedly.
    """

    frame_ready = pyqtSignal(int, np.ndarray)
    error = pyqtSignal(int, str)

    _CONSECUTIVE_FAIL_LIMIT = 10

    def __init__(
        self,
        camera_index: int,
        fps: int = 30,
        parent=None,
        *,
        source: int | str | None = None,
        display_name: str | None = None,
    ):
        super().__init__(parent)
        self.camera_index = camera_index
        self.source = camera_index if source is None else source
        self.display_name = display_name or f"Camera {camera_index}"
        self._fps = max(1, fps)
        self._running = False
        self._mutex = QMutex()

    def run(self):
        cap = self._open_capture()

        if not cap.isOpened():
            self.error.emit(self.camera_index, f"Cannot open {self.display_name}")
            return

        cap.set(cv2.CAP_PROP_FPS, self._fps)
        interval_ms = int(1000 / self._fps)
        consecutive_failures = 0

        with QMutexLocker(self._mutex):
            self._running = True

        while True:
            with QMutexLocker(self._mutex):
                if not self._running:
                    break

            ret, frame = cap.read()

            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= self._CONSECUTIVE_FAIL_LIMIT:
                    self.error.emit(
                        self.camera_index,
                        f"{self.display_name} read failed {consecutive_failures} times",
                    )
                    break
                self.msleep(interval_ms)
                continue

            consecutive_failures = 0
            self.frame_ready.emit(self.camera_index, frame)
            self.msleep(interval_ms)

        cap.release()

    def stop(self):
        with QMutexLocker(self._mutex):
            self._running = False
        self.wait()

    def _open_capture(self):
        if isinstance(self.source, int):
            return cv2.VideoCapture(self.source, cv2.CAP_ANY)
        return cv2.VideoCapture(str(self.source))
