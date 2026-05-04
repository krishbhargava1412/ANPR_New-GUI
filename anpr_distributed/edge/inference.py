"""
YOLOv8 + PaddleOCR inference engine for the Jetson edge node.

Ported from legacy_backend.py with key changes:
  - No PyQt6 dependency (no QThread, no signals)
  - No global singletons — models are owned by the InferenceEngine instance
  - Supports TensorRT engine format for Jetson optimization
  - Batched inference for multi-camera efficiency
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from edge.config import (
    CONFIDENCE_THRESHOLD,
    MODEL_PATH,
    PROXY_RESOLUTION_ENABLED,
    USE_TENSORRT,
    OCR_DIR,
)
from shared.plate_utils import OCR_MIN_SCORE, normalize_plate_text

LOGGER = logging.getLogger("anpr.edge.inference")


def preprocess_plate_crop(crop: np.ndarray) -> np.ndarray:
    """Preprocess a plate crop for OCR. Preserved from legacy_backend.py."""
    if crop is None or getattr(crop, "size", 0) == 0:
        return crop
    image = crop
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    height, width = image.shape[:2]
    if min(height, width) < 32:
        image = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    return image


class InferenceEngine:
    """
    Self-contained inference engine: owns its own YOLO model and OCR reader.
    No global singletons, no locks shared with other threads.
    """

    def __init__(self):
        self._yolo_model = None
        self._ocr_reader = None
        self._confidence_threshold = CONFIDENCE_THRESHOLD
        self._proxy_resolution = PROXY_RESOLUTION_ENABLED

    def load_models(self) -> None:
        """Load YOLO and OCR models. Call once at startup."""
        self._yolo_model = self._load_yolo()
        self._ocr_reader = self._load_ocr()
        LOGGER.info("Models loaded. YOLO: %s | OCR: ready", MODEL_PATH)

    def _load_yolo(self):
        """Load YOLOv8 model — supports both .pt and .engine (TensorRT)."""
        from ultralytics import YOLO
        import torch

        model_path = MODEL_PATH

        # Auto-detect TensorRT engine
        engine_path = Path(model_path).with_suffix(".engine")
        if USE_TENSORRT and engine_path.exists():
            model_path = str(engine_path)
            LOGGER.info("Using TensorRT engine: %s", model_path)
        elif USE_TENSORRT:
            LOGGER.warning(
                "TensorRT requested but .engine not found. "
                "Run: yolo export model=%s format=engine half=True",
                model_path,
            )

        # Allowlist ultralytics model classes for safe loading
        try:
            import ultralytics.nn.tasks as tasks
            add_safe = getattr(torch.serialization, "add_safe_globals", None)
            if add_safe:
                classes = [
                    getattr(tasks, n) for n in
                    ["BaseModel", "DetectionModel", "SegmentationModel"]
                    if hasattr(tasks, n)
                ]
                add_safe(classes)
        except Exception:
            pass

        model = YOLO(model_path)
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        try:
            model.to(device)
        except Exception:
            model.to("cpu")
        LOGGER.info("YOLO loaded on device: %s", device)
        return model

    def _load_ocr(self):
        """Load PaddleOCR reader. Preserves the AwirosAnprReader architecture."""
        import sys

        # Add the old detection directory to path for ppocr import
        detection_dir = Path(__file__).resolve().parents[1] / "app" / "detection"
        if str(detection_dir) not in sys.path:
            sys.path.insert(0, str(detection_dir))

        # Try to import the existing reader
        try:
            from app.detection.legacy_backend import AwirosAnprReader
            reader = AwirosAnprReader()
            LOGGER.info("OCR reader loaded (AwirosAnprReader).")
            return reader
        except ImportError:
            LOGGER.warning(
                "Could not import AwirosAnprReader. "
                "Falling back to standard PaddleOCR."
            )

        # Fallback: use paddleocr directly
        try:
            from paddleocr import PaddleOCR
            reader = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
            LOGGER.info("OCR reader loaded (PaddleOCR fallback).")
            return reader
        except ImportError:
            LOGGER.error("Neither AwirosAnprReader nor PaddleOCR available!")
            return None

    def detect_plates(self, frame: np.ndarray) -> list[dict]:
        """
        Run YOLO detection + OCR on a single frame.
        Ported from detect_plates_in_frame() in legacy_backend.py.
        """
        if self._yolo_model is None:
            return []

        orig_h, orig_w = frame.shape[:2]
        scale_ratio = 1.0
        inference_frame = frame

        if self._proxy_resolution and orig_w > 640:
            scale_ratio = 640.0 / orig_w
            target_h = int(orig_h * scale_ratio)
            inference_frame = cv2.resize(frame, (640, target_h))

        try:
            predictions = self._yolo_model.predict(
                inference_frame, conf=self._confidence_threshold, verbose=False
            )
            boxes = predictions[0].boxes
        except Exception as exc:
            LOGGER.warning("YOLO inference failed: %s", exc)
            return []

        detections = []
        for box in boxes:
            conf = float(box.conf[0])
            if conf < self._confidence_threshold:
                continue

            # Scale bbox back to original resolution
            x1_inf, y1_inf, x2_inf, y2_inf = map(int, box.xyxy[0])
            x1 = max(0, int(x1_inf / scale_ratio))
            y1 = max(0, int(y1_inf / scale_ratio))
            x2 = min(orig_w, int(x2_inf / scale_ratio))
            y2 = min(orig_h, int(y2_inf / scale_ratio))

            if x2 <= x1 or y2 <= y1:
                continue

            # High-resolution crop from original frame
            plate_crop = frame[y1:y2, x1:x2].copy()

            # OCR
            plate_text, ocr_score = self._read_plate(plate_crop)

            detections.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": conf,
                "plate_text": plate_text,
                "ocr_score": ocr_score,
                "plate_crop": plate_crop,
            })

        return detections

    def _read_plate(self, crop: np.ndarray) -> tuple[Optional[str], Optional[float]]:
        """Run OCR on a plate crop. Preserves read_license_plate() logic."""
        if self._ocr_reader is None:
            return None, None

        processed = preprocess_plate_crop(crop)
        try:
            detections = self._ocr_reader.readtext(processed)
        except Exception as exc:
            LOGGER.warning("OCR failed: %s", exc)
            return None, None

        best_text = None
        best_score = 0.0
        for _, text, score in detections:
            score = float(score or 0.0)
            if score < OCR_MIN_SCORE:
                continue
            normalized = normalize_plate_text(text)
            if normalized and score > best_score:
                best_text = normalized
                best_score = score

        return (best_text, best_score) if best_text else (None, None)
