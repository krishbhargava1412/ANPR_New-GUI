from __future__ import annotations

import dataclasses
import time

import numpy as np
from PyQt6.QtCore import QMutex, QMutexLocker, QThread, pyqtSignal

from app.detection.legacy_backend import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PlateVoteTracker,
    append_plate_log,
    detect_plates_in_frame,
    ensure_runtime_dirs,
    get_plate_model,
    get_reader,
    is_watchlist_hit,
    loaded_model_path,
    next_snapshot_path,
    save_plate_snapshot,
)
from app.services.app_runtime import load_ui_settings


@dataclasses.dataclass
class PlateResult:
    camera_index: int
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    timestamp: float
    source: str = ""
    snapshot_path: str = ""
    watchlist_hit: bool = False


@dataclasses.dataclass
class DetectedBox:
    bbox: tuple[int, int, int, int]
    confidence: float


class PlatePipeline(QThread):
    boxes_detected = pyqtSignal(int, list)
    result_ready = pyqtSignal(list)
    status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._frame: np.ndarray | None = None
        self._camera_index: int = -1
        self._running = False
        self._model = None
        self._reader = None
        self._vote_tracker = PlateVoteTracker()
        self._confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
        self._save_snapshots = True

    def submit_frame(self, camera_index: int, frame: np.ndarray):
        with QMutexLocker(self._mutex):
            self._frame = frame.copy()
            self._camera_index = camera_index

    def configure(self, *, confidence_threshold: float | None = None, save_snapshots: bool | None = None):
        with QMutexLocker(self._mutex):
            if confidence_threshold is not None:
                self._confidence_threshold = float(confidence_threshold)
            if save_snapshots is not None:
                self._save_snapshots = bool(save_snapshots)

    def stop(self):
        with QMutexLocker(self._mutex):
            self._running = False
        self.wait()

    def run(self):
        with QMutexLocker(self._mutex):
            self._running = True

        self.status.emit("Loading detection runtime...")
        try:
            ensure_runtime_dirs()
            settings = load_ui_settings()
            self.configure(
                confidence_threshold=float(settings["confidence_threshold"]),
                save_snapshots=bool(settings["save_snapshots"]),
            )
            self._model = get_plate_model()
            self._reader = get_reader()
        except Exception as exc:  # noqa: BLE001
            self.status.emit(f"Runtime load failed: {exc}")
            return

        self.status.emit(f"Detection ready | model: {loaded_model_path()}")

        while True:
            with QMutexLocker(self._mutex):
                if not self._running:
                    break
                frame = self._frame
                camera_index = self._camera_index
                self._frame = None

            if frame is None:
                self.msleep(20)
                continue

            try:
                self._process_frame(frame, camera_index)
            except Exception as exc:  # noqa: BLE001
                self.status.emit(f"Pipeline error: {exc}")

    def _process_frame(self, frame: np.ndarray, camera_index: int):
        detections = detect_plates_in_frame(
            self._model,
            frame,
            confidence_threshold=self._confidence_threshold,
        )
        if not detections:
            return

        boxes = [
            DetectedBox(bbox=detection["bbox"], confidence=float(detection["confidence"]))
            for detection in detections
        ]
        self.boxes_detected.emit(camera_index, boxes)

        source = f"Camera {camera_index}"
        results: list[PlateResult] = []
        for detection in detections:
            plate_text = detection.get("plate_text")
            if not plate_text:
                continue

            stable_text = self._vote_tracker.register(
                source,
                detection["bbox"],
                str(plate_text),
                float(detection.get("confidence") or 0.0),
            )
            if not stable_text:
                continue

            timestamp = time.time()
            watchlist_hit = is_watchlist_hit(stable_text)
            saved_snapshot = None
            if self._save_snapshots:
                snapshot_path = next_snapshot_path(stable_text, source)
                saved_snapshot = save_plate_snapshot(detection.get("plate_crop"), snapshot_path)
            append_plate_log(
                stable_text,
                source=source,
                confidence=float(detection.get("confidence") or 0.0),
                snapshot_path=saved_snapshot,
                watchlist_hit=watchlist_hit,
            )
            results.append(
                PlateResult(
                    camera_index=camera_index,
                    text=stable_text,
                    confidence=float(detection.get("confidence") or 0.0),
                    bbox=detection["bbox"],
                    timestamp=timestamp,
                    source=source,
                    snapshot_path=str(saved_snapshot or ""),
                    watchlist_hit=watchlist_hit,
                )
            )

        if results:
            self.result_ready.emit(results)
