"""
Plate detection pipeline.

Runs in a QThread. For each frame:
  1. YOLOv8 detects license plate bounding boxes — emits boxes_detected immediately.
  2. Each crop is preprocessed and passed to Tesseract.
  3. Confirmed results emitted via result_ready.

The model is loaded once on first run() call (lazy, so UI stays responsive).
"""

from __future__ import annotations

import re
import time
import dataclasses

import cv2
import numpy as np
import pytesseract

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


@dataclasses.dataclass
class PlateResult:
    camera_index: int
    text: str                        # cleaned OCR text
    confidence: float                # YOLO box confidence
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in original frame
    timestamp: float                 # time.time()


@dataclasses.dataclass
class DetectedBox:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float


class PlatePipeline(QThread):
    """
    Signals:
        boxes_detected(int, list[DetectedBox])  — emitted right after YOLO, before OCR
        result_ready(list[PlateResult])         — emitted after OCR completes
        status(str)                             — loading / error messages
    """

    boxes_detected = pyqtSignal(int, list)   # (camera_index, list[DetectedBox])
    result_ready   = pyqtSignal(list)        # list[PlateResult]
    status         = pyqtSignal(str)

    _MODEL_NAME       = "keremberke/yolov8n-license-plate-detection"
    _CONF_THRESHOLD   = 0.4
    _TESSERACT_CONFIG = (
        "--oem 3 --psm 7 "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._frame: np.ndarray | None = None
        self._camera_index: int = -1
        self._running = False
        self._model = None

    # ------------------------------------------------------------------
    # Public API — called from main thread
    # ------------------------------------------------------------------

    def submit_frame(self, camera_index: int, frame: np.ndarray):
        """Replace pending frame with newest. Older unprocessed frames are dropped."""
        with QMutexLocker(self._mutex):
            self._frame = frame.copy()
            self._camera_index = camera_index

    def stop(self):
        with QMutexLocker(self._mutex):
            self._running = False
        self.wait()

    # ------------------------------------------------------------------
    # Thread loop
    # ------------------------------------------------------------------

    def run(self):
        with QMutexLocker(self._mutex):
            self._running = True

        self.status.emit("Loading model...")
        try:
            self._model = self._load_model()
        except Exception as exc:
            self.status.emit(f"Model load failed: {exc}")
            return

        self.status.emit("Model ready")

        while True:
            with QMutexLocker(self._mutex):
                if not self._running:
                    break
                frame = self._frame
                cam_idx = self._camera_index
                self._frame = None

            if frame is None:
                self.msleep(20)
                continue

            try:
                self._process(frame, cam_idx)
            except Exception as exc:
                self.status.emit(f"Pipeline error: {exc}")

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self):
        from ultralyticsplus import YOLO
        model = YOLO(self._MODEL_NAME)
        model.overrides["conf"] = self._CONF_THRESHOLD
        model.overrides["iou"] = 0.45
        model.overrides["max_det"] = 10
        return model

    # ------------------------------------------------------------------
    # Per-frame processing — two phases
    # ------------------------------------------------------------------

    def _process(self, frame: np.ndarray, camera_index: int):
        # --- Phase 1: YOLO detection ---
        predictions = self._model.predict(frame, verbose=False)

        raw_boxes: list[tuple[int, int, int, int, float]] = []
        for pred in predictions:
            if pred.boxes is None:
                continue
            for box in pred.boxes:
                conf = float(box.conf[0])
                if conf < self._CONF_THRESHOLD:
                    continue
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                raw_boxes.append((x1, y1, x2, y2, conf))

        if not raw_boxes:
            return

        # Emit SCANNING state immediately — before OCR blocks
        detected = [DetectedBox(bbox=(x1, y1, x2, y2), confidence=conf)
                    for x1, y1, x2, y2, conf in raw_boxes]
        self.boxes_detected.emit(camera_index, detected)

        # --- Phase 2: OCR per crop ---
        results: list[PlateResult] = []
        for x1, y1, x2, y2, conf in raw_boxes:
            crop = self._extract_crop(frame, x1, y1, x2, y2)
            if crop is None:
                continue
            text = self._ocr(crop)
            if not text:
                continue
            results.append(PlateResult(
                camera_index=camera_index,
                text=text,
                confidence=conf,
                bbox=(x1, y1, x2, y2),
                timestamp=time.time(),
            ))

        if results:
            self.result_ready.emit(results)

    def _extract_crop(
        self,
        frame: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
        pad: int = 6,
    ) -> np.ndarray | None:
        h, w = frame.shape[:2]
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)
        if x2 <= x1 or y2 <= y1:
            return None
        return self._preprocess_crop(frame[y1:y2, x1:x2])

    @staticmethod
    def _preprocess_crop(crop: np.ndarray) -> np.ndarray:
        scale = max(1, 200 // max(crop.shape[0], crop.shape[1], 1))
        if scale > 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        _, thresh = cv2.threshold(gray, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def _ocr(self, image: np.ndarray) -> str:
        raw = pytesseract.image_to_string(image, config=self._TESSERACT_CONFIG)
        return self._clean(raw)

    @staticmethod
    def _clean(text: str) -> str:
        text = text.upper().strip()
        text = re.sub(r"[^A-Z0-9]", "", text)
        return text if len(text) >= 3 else ""