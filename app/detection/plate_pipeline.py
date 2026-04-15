from __future__ import annotations

import dataclasses
import time
import traceback

import numpy as np
from PyQt6.QtCore import QMutex, QMutexLocker, QThread, pyqtSignal

from app.detection.legacy_backend import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PlateVoteTracker,
    detect_plates_in_frame,
    ensure_runtime_dirs,
    get_plate_model,
    get_reader,
    is_watchlist_hit,
    loaded_model_path,
    validate_detection_runtime,
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
    plate_crop: np.ndarray | None = None


@dataclasses.dataclass
class DetectedBox:
    bbox: tuple[int, int, int, int]
    confidence: float


class PlatePipeline(QThread):
    boxes_detected = pyqtSignal(int, list)
    result_ready = pyqtSignal(list)
    status = pyqtSignal(str)
    telemetry = pyqtSignal(int, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._frame: np.ndarray | None = None
        self._camera_index: int = -1
        self._source_label = ""
        self._running = False
        self._paused = False
        self._model = None
        self._reader = None
        self._vote_tracker = PlateVoteTracker()
        self._confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD

    def submit_frame(self, camera_index: int, frame: np.ndarray, source_label: str = ""):
        with QMutexLocker(self._mutex):
            self._frame = frame.copy()
            self._camera_index = camera_index
            self._source_label = source_label or f"Camera {camera_index}"

    def configure(self, *, confidence_threshold: float | None = None):
        with QMutexLocker(self._mutex):
            if confidence_threshold is not None:
                self._confidence_threshold = float(confidence_threshold)

    def set_paused(self, paused: bool):
        with QMutexLocker(self._mutex):
            self._paused = paused

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
            validate_detection_runtime()
            settings = load_ui_settings()
            self.configure(
                confidence_threshold=float(settings["confidence_threshold"]),
            )
            self._model = get_plate_model()
            self._reader = get_reader()
        except Exception as exc:  # noqa: BLE001
            details = f"{type(exc).__name__}: {exc}".strip()
            self.status.emit(f"Runtime load failed: {details}")
            traceback.print_exc()
            return

        self.status.emit(f"Detection ready | model: {loaded_model_path()}")

        while True:
            with QMutexLocker(self._mutex):
                if not self._running:
                    break
                paused = self._paused
                frame = self._frame
                camera_index = self._camera_index
                source_label = self._source_label
                self._frame = None

            if paused:
                self.msleep(20)
                continue
            if frame is None:
                self.msleep(20)
                continue

            try:
                self._process_frame(frame, camera_index, source_label)
            except Exception as exc:  # noqa: BLE001
                self.status.emit(f"Pipeline error: {exc}")

    def _process_frame(self, frame: np.ndarray, camera_index: int, source_label: str):
        started = time.perf_counter()
        detections = detect_plates_in_frame(
            self._model,
            frame,
            confidence_threshold=self._confidence_threshold,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.telemetry.emit(
            camera_index,
            {
                "latency_ms": elapsed_ms,
                "box_count": len(detections),
                "source": source_label or f"Camera {camera_index}",
            },
        )
        if not detections:
            return

        boxes = [
            DetectedBox(bbox=detection["bbox"], confidence=float(detection["confidence"]))
            for detection in detections
        ]
        self.boxes_detected.emit(camera_index, boxes)

        source = source_label or f"Camera {camera_index}"
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
            results.append(
                PlateResult(
                    camera_index=camera_index,
                    text=stable_text,
                    confidence=float(detection.get("confidence") or 0.0),
                    bbox=detection["bbox"],
                    timestamp=timestamp,
                    source=source,
                    snapshot_path="",
                    watchlist_hit=watchlist_hit,
                    plate_crop=detection.get("plate_crop"),
                )
            )

        if results:
            self.telemetry.emit(
                camera_index,
                {
                    "latency_ms": elapsed_ms,
                    "box_count": len(detections),
                    "result_count": len(results),
                    "source": source,
                },
            )
            self.result_ready.emit(results)
