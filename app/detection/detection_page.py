"""
Detection page.

Layout (horizontal split):
  Left  — camera feed with bounding box overlay (2/3 width)
  Right — LogPanel (1/3 width)

Box states:
  SCANNING  — yellow box + SCANNING... label. Set when boxes_detected fires.
  CONFIRMED — green box + plate text + confidence. Set when result_ready fires.
              Auto-expires after _CONFIRMED_TTL_SEC seconds.
"""

from __future__ import annotations

import time
import enum

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QFrame, QSizePolicy, QSpacerItem, QComboBox
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap

from app.detection.plate_pipeline import PlatePipeline, PlateResult, DetectedBox
from app.utils.log_panel import LogPanel


class BoxState(enum.Enum):
    SCANNING  = "scanning"
    CONFIRMED = "confirmed"


# BGR colors
_COLOR_SCANNING  = (0, 200, 255)   # yellow
_COLOR_CONFIRMED = (0, 230, 0)     # green
_FONT             = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE       = 0.55
_FONT_THICKNESS   = 1


class _BoxEntry:
    """Tracks one detected plate box and its current state."""

    __slots__ = ("bbox", "confidence", "state", "text", "confirmed_at")

    def __init__(self, bbox: tuple[int, int, int, int], confidence: float):
        self.bbox        = bbox
        self.confidence  = confidence
        self.state       = BoxState.SCANNING
        self.text        = ""
        self.confirmed_at: float | None = None

    def confirm(self, text: str):
        self.text         = text
        self.state        = BoxState.CONFIRMED
        self.confirmed_at = time.monotonic()

    def is_expired(self, ttl: float) -> bool:
        if self.state is not BoxState.CONFIRMED:
            return False
        return (time.monotonic() - self.confirmed_at) > ttl


def _iou(a: tuple, b: tuple) -> float:
    """Intersection-over-union for two (x1,y1,x2,y2) boxes."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


class FeedWidget(QLabel):
    """
    Displays camera frames with state-aware bounding box overlay.
    Maintains its own _BoxEntry list; updated by set_scanning / set_confirmed.
    """

    _CONFIRMED_TTL_SEC = 2.0
    _IOU_MATCH_THRESH  = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("feedWidget")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("NO FEED\n\nSelect a camera and press START")
        self.setMinimumSize(QSize(480, 320))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._entries: list[_BoxEntry] = []

    def set_scanning(self, boxes: list[DetectedBox]):
        """Called immediately after YOLO — before OCR. Replaces all current entries."""
        self._entries = [_BoxEntry(b.bbox, b.confidence) for b in boxes]

    def set_confirmed(self, results: list[PlateResult]):
        """
        Called after OCR. Matches each result to the nearest SCANNING entry by
        IoU and promotes it to CONFIRMED. Unmatched results create new entries.
        """
        for result in results:
            best_idx = -1
            best_iou = self._IOU_MATCH_THRESH
            for i, entry in enumerate(self._entries):
                score = _iou(entry.bbox, result.bbox)
                if score > best_iou:
                    best_iou = score
                    best_idx = i

            if best_idx >= 0:
                self._entries[best_idx].confirm(result.text)
            else:
                new_entry = _BoxEntry(result.bbox, result.confidence)
                new_entry.confirm(result.text)
                self._entries.append(new_entry)

    def clear_boxes(self):
        self._entries.clear()

    def update_frame(self, frame: np.ndarray):
        self._expire_confirmed()
        annotated = self._draw(frame)
        h, w, ch = annotated.shape
        qt_img = QImage(annotated.data, w, h, ch * w, QImage.Format.Format_BGR888)
        pixmap = QPixmap.fromImage(qt_img)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.setPixmap(scaled)

    def _expire_confirmed(self):
        self._entries = [
            e for e in self._entries
            if not e.is_expired(self._CONFIRMED_TTL_SEC)
        ]

    def _draw(self, frame: np.ndarray) -> np.ndarray:
        if not self._entries:
            return frame

        out = frame.copy()
        for entry in self._entries:
            x1, y1, x2, y2 = entry.bbox

            if entry.state is BoxState.SCANNING:
                color = _COLOR_SCANNING
                label = "SCANNING..."
            else:
                color = _COLOR_CONFIRMED
                label = f"{entry.text}  {entry.confidence:.0%}"

            # box
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            # corner brackets (4 corners, 12px arms)
            arm = 12
            t   = 3
            corners = [
                ((x1, y1), (x1 + arm, y1), (x1, y1 + arm)),
                ((x2, y1), (x2 - arm, y1), (x2, y1 + arm)),
                ((x1, y2), (x1 + arm, y2), (x1, y2 - arm)),
                ((x2, y2), (x2 - arm, y2), (x2, y2 - arm)),
            ]
            for corner, h_pt, v_pt in corners:
                cv2.line(out, corner, h_pt, color, t)
                cv2.line(out, corner, v_pt, color, t)

            # label background + text
            (tw, th), _ = cv2.getTextSize(label, _FONT, _FONT_SCALE, _FONT_THICKNESS)
            bg_y1 = max(y1 - th - 8, 0)
            cv2.rectangle(out, (x1, bg_y1), (x1 + tw + 8, y1), color, -1)
            cv2.putText(
                out, label,
                (x1 + 4, y1 - 4),
                _FONT, _FONT_SCALE,
                (0, 0, 0), _FONT_THICKNESS, cv2.LINE_AA,
            )

        return out


class DetectionPage(QWidget):
    """Owns PlatePipeline. Receives frames externally via on_frame_ready()."""

    _FRAME_SKIP = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._pipeline: PlatePipeline | None = None
        self._frame_counter = 0
        self._active_camera: int | None = None
        self._running = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 24)
        root.setSpacing(0)

        header_row = QHBoxLayout()
        title = QLabel("License Plate Detection")
        title.setObjectName("pageTitle")
        subtitle = QLabel("YOLOv8 detection + Tesseract OCR on live camera feed")
        subtitle.setObjectName("pageSubtitle")

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_row.addLayout(title_col)
        header_row.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        root.addLayout(header_row)
        root.addSpacing(20)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        self._cam_combo = QComboBox()
        self._cam_combo.setObjectName("cameraCombo")
        self._cam_combo.setFixedHeight(36)
        self._cam_combo.setMinimumWidth(160)
        self._cam_combo.setPlaceholderText("Select camera")
        ctrl.addWidget(self._cam_combo)

        self._start_btn = QPushButton("START")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._toggle_pipeline)
        ctrl.addWidget(self._start_btn)

        ctrl.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )

        self._status_label = QLabel("Idle")
        self._status_label.setObjectName("pageSubtitle")
        ctrl.addWidget(self._status_label)

        root.addLayout(ctrl)
        root.addSpacing(16)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)
        root.addSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("detectionSplitter")
        splitter.setHandleWidth(1)

        self._feed = FeedWidget()
        splitter.addWidget(self._feed)

        self._log_panel = LogPanel()
        self._log_panel.setMinimumWidth(280)
        splitter.addWidget(self._log_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------
    # Called by MainWindow when camera workers emit frames
    # ------------------------------------------------------------------

    def register_camera(self, index: int):
        for i in range(self._cam_combo.count()):
            if self._cam_combo.itemData(i) == index:
                return
        self._cam_combo.addItem(f"Camera {index}", userData=index)
        self._start_btn.setEnabled(True)

    def unregister_camera(self, index: int):
        for i in range(self._cam_combo.count()):
            if self._cam_combo.itemData(i) == index:
                self._cam_combo.removeItem(i)
                break
        if self._active_camera == index:
            self._stop_pipeline()
        if self._cam_combo.count() == 0:
            self._start_btn.setEnabled(False)

    @pyqtSlot(int, np.ndarray)
    def on_frame_ready(self, camera_index: int, frame: np.ndarray):
        if camera_index != self._active_camera:
            return

        self._feed.update_frame(frame)

        if not self._running or self._pipeline is None:
            return

        self._frame_counter += 1
        if self._frame_counter % self._FRAME_SKIP == 0:
            self._pipeline.submit_frame(camera_index, frame)

    # ------------------------------------------------------------------
    # Pipeline control
    # ------------------------------------------------------------------

    def _toggle_pipeline(self):
        if self._running:
            self._stop_pipeline()
        else:
            self._start_pipeline()

    def _start_pipeline(self):
        idx = self._cam_combo.currentData()
        if idx is None:
            return

        self._active_camera = idx
        self._pipeline = PlatePipeline()
        self._pipeline.boxes_detected.connect(self._on_boxes_detected)
        self._pipeline.result_ready.connect(self._on_results)
        self._pipeline.status.connect(self._on_pipeline_status)
        self._pipeline.start()

        self._running = True
        self._start_btn.setText("STOP")
        self._status_label.setText("Loading model...")

    def _stop_pipeline(self):
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None

        self._running = False
        self._active_camera = None
        self._feed.clear_boxes()
        self._start_btn.setText("START")
        self._status_label.setText("Stopped")

    # ------------------------------------------------------------------
    # Pipeline signals
    # ------------------------------------------------------------------

    @pyqtSlot(int, list)
    def _on_boxes_detected(self, camera_index: int, boxes: list[DetectedBox]):
        """Phase 1 — YOLO done, OCR not yet started. Show SCANNING state."""
        if camera_index != self._active_camera:
            return
        self._feed.set_scanning(boxes)
        self._status_label.setText(f"Scanning {len(boxes)} plate(s)...")

    @pyqtSlot(list)
    def _on_results(self, results: list[PlateResult]):
        """Phase 2 — OCR done. Promote matching boxes to CONFIRMED."""
        self._feed.set_confirmed(results)
        self._log_panel.add_results(results)
        self._status_label.setText(f"Confirmed {len(results)} plate(s)")

    @pyqtSlot(str)
    def _on_pipeline_status(self, message: str):
        self._status_label.setText(message)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._stop_pipeline()
        super().closeEvent(event)
