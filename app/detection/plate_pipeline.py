"""Detection pipeline — stdlib threading version (replaces QThread)."""

from __future__ import annotations

import dataclasses
import time
import traceback
from threading import Lock, Thread
from typing import Callable, Optional

import numpy as np

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
    snapshot_id: int | None = None
    watchlist_hit: bool = False
    plate_crop: np.ndarray | None = None


@dataclasses.dataclass
class DetectedBox:
    bbox: tuple[int, int, int, int]
    confidence: float


class PlatePipeline(Thread):
    def __init__(
        self,
        *,
        on_boxes: Optional[Callable[[int, list[DetectedBox]], None]] = None,
        on_results: Optional[Callable[[list[PlateResult]], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_telemetry: Optional[Callable[[int, dict], None]] = None,
    ):
        super().__init__(daemon=True, name="PlatePipeline")
        self._lock = Lock()
        self._frame: np.ndarray | None = None
        self._camera_index: int = -1
        self._source_label = ""
        self._running = False
        self._paused = False
        self._model = None
        self._reader = None
        self._vote_tracker = PlateVoteTracker()
        self._confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
        self._proxy_resolution_enabled = True

        # Callbacks (replace pyqtSignals)
        self._on_boxes = on_boxes
        self._on_results = on_results
        self._on_status = on_status
        self._on_telemetry = on_telemetry

    def submit_frame(self, camera_index: int, frame: np.ndarray, source_label: str = ""):
        with self._lock:
            self._frame = frame.copy()
            self._camera_index = camera_index
            self._source_label = source_label or f"Camera {camera_index}"

    def configure(self, *, confidence_threshold: float | None = None, proxy_resolution_enabled: bool | None = None):
        with self._lock:
            if confidence_threshold is not None:
                self._confidence_threshold = float(confidence_threshold)
            if proxy_resolution_enabled is not None:
                self._proxy_resolution_enabled = bool(proxy_resolution_enabled)

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = paused

    def stop(self):
        with self._lock:
            self._running = False
        self.join(timeout=10)

    def _emit_status(self, msg: str):
        if self._on_status:
            self._on_status(msg)

    def run(self):
        with self._lock:
            self._running = True

        self._emit_status("Loading detection runtime...")
        try:
            ensure_runtime_dirs()
            validate_detection_runtime()
            settings = load_ui_settings()
            self.configure(
                confidence_threshold=float(settings["confidence_threshold"]),
                proxy_resolution_enabled=bool(settings.get("proxy_resolution_enabled", True)),
            )
            self._model = get_plate_model()
            self._reader = get_reader()
        except Exception as exc:
            details = f"{type(exc).__name__}: {exc}".strip()
            self._emit_status(f"Runtime load failed: {details}")
            traceback.print_exc()
            return

        self._emit_status(f"Detection ready | model: {loaded_model_path()}")

        while True:
            with self._lock:
                if not self._running:
                    break
                paused = self._paused
                frame = self._frame
                camera_index = self._camera_index
                source_label = self._source_label
                self._frame = None

            if paused:
                time.sleep(0.02)
                continue
            if frame is None:
                time.sleep(0.02)
                continue

            try:
                self._process_frame(frame, camera_index, source_label)
            except Exception as exc:
                self._emit_status(f"Pipeline error: {exc}")

    def _process_frame(self, frame: np.ndarray, camera_index: int, source_label: str):
        current_model = get_plate_model()
        if current_model is not self._model:
            self._model = current_model
            self._emit_status(f"Detection ready | model: {loaded_model_path()}")

        started = time.perf_counter()
        detections = detect_plates_in_frame(
            self._model,
            frame,
            confidence_threshold=self._confidence_threshold,
            proxy_resolution_enabled=self._proxy_resolution_enabled,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        if self._on_telemetry:
            self._on_telemetry(
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
        if self._on_boxes:
            self._on_boxes(camera_index, boxes)

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
                    snapshot_id=None,
                    watchlist_hit=watchlist_hit,
                    plate_crop=detection.get("plate_crop"),
                )
            )

        if results:
            if self._on_telemetry:
                self._on_telemetry(
                    camera_index,
                    {
                        "latency_ms": elapsed_ms,
                        "box_count": len(detections),
                        "result_count": len(results),
                        "source": source,
                    },
                )
            if self._on_results:
                self._on_results(results)
