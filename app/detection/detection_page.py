"""
Detection page.

Layout (horizontal split):
  Left  - selected camera feed with bounding box overlay
  Right - LogPanel

This page now supports simultaneous background detection for every active
camera. The combo box simply selects which camera's annotated state is shown in
the main viewer.
"""

from __future__ import annotations

import enum
import time
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtCore import QSize, Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.detection.plate_pipeline import DetectedBox, PlatePipeline, PlateResult
from app.detection.legacy_backend import append_plate_log, next_snapshot_path, save_plate_snapshot
from app.services.app_runtime import load_ui_settings, clear_plate_log
from app.utils.log_panel import LogPanel


class BoxState(enum.Enum):
    SCANNING = "scanning"
    CONFIRMED = "confirmed"


_COLOR_SCANNING = (0, 200, 255)
_COLOR_CONFIRMED = (0, 230, 0)
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.55
_FONT_THICKNESS = 1


class _BoxEntry:
    __slots__ = ("bbox", "confidence", "state", "text", "confirmed_at", "updated_at")

    def __init__(self, bbox: tuple[int, int, int, int], confidence: float):
        self.bbox = bbox
        self.confidence = confidence
        self.state = BoxState.SCANNING
        self.text = ""
        self.confirmed_at: float | None = None
        self.updated_at = time.monotonic()

    def confirm(self, text: str):
        self.text = text
        self.state = BoxState.CONFIRMED
        self.confirmed_at = time.monotonic()
        self.updated_at = time.monotonic()

    def is_expired(self, scan_ttl: float, confirm_ttl: float) -> bool:
        if self.state == BoxState.CONFIRMED and self.confirmed_at is not None:
            return (time.monotonic() - self.confirmed_at) > confirm_ttl
        return (time.monotonic() - self.updated_at) > scan_ttl


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
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
    _CONFIRMED_TTL_SEC = 2.0
    _SCANNING_TTL_SEC = 1.0
    _IOU_MATCH_THRESH = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("feedWidget")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("NO FEED\n\nSave cameras in Settings and press START DETECTION")
        self.setMinimumSize(QSize(480, 320))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._entries: list[_BoxEntry] = []

    def set_scanning(self, boxes: list[DetectedBox]):
        matched_indices = set()
        for box in boxes:
            best_idx = -1
            best_iou = self._IOU_MATCH_THRESH
            for idx, entry in enumerate(self._entries):
                if idx in matched_indices:
                    continue
                score = _iou(entry.bbox, box.bbox)
                if score > best_iou:
                    best_iou = score
                    best_idx = idx
            if best_idx >= 0:
                self._entries[best_idx].bbox = box.bbox
                self._entries[best_idx].confidence = box.confidence
                self._entries[best_idx].updated_at = time.monotonic()
                self._entries[best_idx].state = BoxState.SCANNING
                matched_indices.add(best_idx)
            else:
                self._entries.append(_BoxEntry(box.bbox, box.confidence))

    def set_confirmed(self, results: list[PlateResult]):
        for result in results:
            best_idx = -1
            best_iou = self._IOU_MATCH_THRESH
            for idx, entry in enumerate(self._entries):
                score = _iou(entry.bbox, result.bbox)
                if score > best_iou:
                    best_iou = score
                    best_idx = idx
            if best_idx >= 0:
                self._entries[best_idx].confirm(result.text)
            else:
                entry = _BoxEntry(result.bbox, result.confidence)
                entry.confirm(result.text)
                self._entries.append(entry)

    def clear_boxes(self):
        self._entries.clear()

    def update_frame(self, frame: np.ndarray):
        self._entries = [
            entry
            for entry in self._entries
            if not entry.is_expired(self._SCANNING_TTL_SEC, self._CONFIRMED_TTL_SEC)
        ]
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

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            arm = 12
            thickness = 3
            corners = [
                ((x1, y1), (x1 + arm, y1), (x1, y1 + arm)),
                ((x2, y1), (x2 - arm, y1), (x2, y1 + arm)),
                ((x1, y2), (x1 + arm, y2), (x1, y2 - arm)),
                ((x2, y2), (x2 - arm, y2), (x2, y2 - arm)),
            ]
            for corner, h_pt, v_pt in corners:
                cv2.line(out, corner, h_pt, color, thickness)
                cv2.line(out, corner, v_pt, color, thickness)

            (tw, th), _ = cv2.getTextSize(label, _FONT, _FONT_SCALE, _FONT_THICKNESS)
            bg_y1 = max(y1 - th - 8, 0)
            cv2.rectangle(out, (x1, bg_y1), (x1 + tw + 8, y1), color, -1)
            cv2.putText(
                out,
                label,
                (x1 + 4, y1 - 4),
                _FONT,
                _FONT_SCALE,
                (0, 0, 0),
                _FONT_THICKNESS,
                cv2.LINE_AA,
            )
        return out


class DetectionPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._pipelines: dict[int, PlatePipeline] = {}
        self._frame_counters: dict[int, int] = {}
        self._latest_frames: dict[int, np.ndarray] = {}
        self._last_boxes: dict[int, list[DetectedBox]] = {}
        self._last_results: dict[int, list[PlateResult]] = {}
        self._camera_status: dict[int, str] = {}
        self._source_labels: dict[int, str] = {}
        self._registered_cameras: list[int] = []
        self._active_camera: int | None = None
        self._running = False
        self._review_in_progress = False
        self._pending_results: list[PlateResult] = []
        self._frame_skip = int(load_ui_settings()["frame_skip"])
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 24)
        root.setSpacing(0)

        header_row = QHBoxLayout()
        title = QLabel("License Plate Detection")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Simultaneous multi-camera detection using the legacy ANPR backend"
        )
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

        self._start_btn = QPushButton("START DETECTION")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._toggle_detection)
        self._start_btn.setEnabled(False)
        ctrl.addWidget(self._start_btn)

        ctrl.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )

        self._status_label = QLabel("Idle - Select camera from Cameras page to begin")
        self._status_label.setObjectName("pageSubtitle")
        ctrl.addWidget(self._status_label)

        self._log_panel = LogPanel()

        clear_btn = QPushButton("CLEAR LOG")
        clear_btn.setObjectName("secondaryButton")
        clear_btn.setFixedHeight(36)
        clear_btn.clicked.connect(self._on_clear_log)
        ctrl.addWidget(clear_btn)

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

        self._log_panel.setMinimumWidth(280)
        splitter.addWidget(self._log_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

    def register_camera(self, index: int, label: str | None = None):
        if index in self._registered_cameras:
            if label:
                self._source_labels[index] = label
            return
        self._registered_cameras.append(index)
        self._source_labels[index] = label or f"CAM {index}"
        self._camera_status[index] = "Idle"
        self._start_btn.setEnabled(True)
        if self._active_camera is None:
            self._active_camera = index
            self._restore_selected_camera_state()
        if self._running:
            self._start_pipeline_for_camera(index)
        self._update_status_text()

    def unregister_camera(self, index: int):
        self._stop_pipeline_for_camera(index)
        self._frame_counters.pop(index, None)
        self._latest_frames.pop(index, None)
        self._last_boxes.pop(index, None)
        self._last_results.pop(index, None)
        self._camera_status.pop(index, None)
        self._source_labels.pop(index, None)
        if index in self._registered_cameras:
            self._registered_cameras.remove(index)
        if self._active_camera == index:
            self._active_camera = (
                self._registered_cameras[0] if self._registered_cameras else None
            )
            self._restore_selected_camera_state()
        self._start_btn.setEnabled(len(self._registered_cameras) > 0)
        self._update_status_text()

    @pyqtSlot(int, np.ndarray)
    def on_frame_ready(self, camera_index: int, frame: np.ndarray):
        self._latest_frames[camera_index] = frame.copy()
        if camera_index == self._active_camera:
            self._feed.update_frame(frame)
        if not self._running:
            return
        pipeline = self._pipelines.get(camera_index)
        if pipeline is None:
            return
        self._frame_counters[camera_index] = (
            self._frame_counters.get(camera_index, 0) + 1
        )
        if self._frame_counters[camera_index] % self._frame_skip == 0:
            if self._review_in_progress:
                return
            pipeline.submit_frame(
                camera_index,
                frame,
                self._source_labels.get(camera_index, f"CAM {camera_index}"),
            )

    def apply_runtime_settings(self, settings: dict[str, object]):
        self._frame_skip = max(1, int(settings.get("frame_skip", self._frame_skip)))
        for pipeline in self._pipelines.values():
            pipeline.configure(
                confidence_threshold=float(settings.get("confidence_threshold", 0.5)),
            )

    def _toggle_detection(self):
        if self._running:
            self._stop_all_pipelines()
        else:
            self._start_all_pipelines()

    def start_detection(self):
        if not self._running and len(self._registered_cameras) > 0:
            self._start_all_pipelines()

    def stop_detection(self):
        if self._running:
            self._stop_all_pipelines()

    def _start_all_pipelines(self):
        if len(self._registered_cameras) == 0:
            return
        self._running = True
        for camera_index in self._registered_cameras:
            self._start_pipeline_for_camera(camera_index)
        self._start_btn.setText("STOP DETECTION")
        self._update_status_text()

    def _stop_all_pipelines(self):
        for camera_index in list(self._pipelines):
            self._stop_pipeline_for_camera(camera_index)
        self._running = False
        self._pending_results.clear()
        self._review_in_progress = False
        self._feed.clear_boxes()
        self._start_btn.setText("START DETECTION")
        self._update_status_text()

    def _start_pipeline_for_camera(self, camera_index: int):
        if camera_index in self._pipelines:
            return
        pipeline = PlatePipeline()
        pipeline.boxes_detected.connect(self._on_boxes_detected)
        pipeline.result_ready.connect(self._on_results)
        pipeline.status.connect(
            lambda message, cam=camera_index: self._on_pipeline_status(cam, message)
        )
        pipeline.configure(
            confidence_threshold=float(load_ui_settings()["confidence_threshold"]),
        )
        self._pipelines[camera_index] = pipeline
        self._frame_counters[camera_index] = 0
        self._camera_status[camera_index] = "Loading..."
        pipeline.start()

    def _stop_pipeline_for_camera(self, camera_index: int):
        pipeline = self._pipelines.pop(camera_index, None)
        if pipeline is not None:
            pipeline.stop()
        self._camera_status[camera_index] = "Stopped"

    def _on_camera_selected(self):
        pass

    def _restore_selected_camera_state(self):
        if self._active_camera is None:
            self._feed.clear_boxes()
            self._feed.setText("NO FEED\n\nSave local or IP/RTSP cameras in Settings")
            return
        boxes = self._last_boxes.get(self._active_camera, [])
        results = self._last_results.get(self._active_camera, [])
        self._feed.set_scanning(boxes)
        self._feed.set_confirmed(results)
        frame = self._latest_frames.get(self._active_camera)
        if frame is not None:
            self._feed.update_frame(frame)

    @pyqtSlot(int, list)
    def _on_boxes_detected(self, camera_index: int, boxes: list[DetectedBox]):
        self._last_boxes[camera_index] = boxes
        if camera_index == self._active_camera:
            self._feed.set_scanning(boxes)
            frame = self._latest_frames.get(camera_index)
            if frame is not None:
                self._feed.update_frame(frame)
        self._camera_status[camera_index] = f"Scanning {len(boxes)} plate(s)"
        self._update_status_text()

    @pyqtSlot(list)
    def _on_results(self, results: list[PlateResult]):
        if not results:
            return
        self._pending_results.extend(results)
        self._set_pipeline_pause(True)
        if not self._review_in_progress:
            self._process_pending_results()

    def _on_pipeline_status(self, camera_index: int, message: str):
        self._camera_status[camera_index] = message
        self._update_status_text()

    def _set_pipeline_pause(self, paused: bool):
        for pipeline in self._pipelines.values():
            pipeline.set_paused(paused)

    def _process_pending_results(self):
        if self._review_in_progress:
            return
        if not self._pending_results:
            self._set_pipeline_pause(False)
            return

        self._review_in_progress = True
        result = self._pending_results.pop(0)
        camera_index = result.camera_index
        self._camera_status[camera_index] = f"Waiting to save {result.text}"
        self._update_status_text()
        self._last_results[camera_index] = [result]
        if camera_index == self._active_camera:
            self._feed.set_confirmed([result])
            frame = self._latest_frames.get(camera_index)
            if frame is not None:
                self._feed.update_frame(frame)

        saved_snapshot = ""
        if bool(load_ui_settings().get("save_snapshots", True)):
            decision = QMessageBox(self)
            decision.setIcon(QMessageBox.Icon.Question)
            decision.setWindowTitle("Save Snapshot")
            decision.setText(f"Detected plate {result.text} from {result.source}.")
            decision.setInformativeText(
                "Save this snapshot now? Detection will resume after you save or skip this plate."
            )
            save_button = decision.addButton(
                "Save Snapshot", QMessageBox.ButtonRole.AcceptRole
            )
            skip_button = decision.addButton("Skip", QMessageBox.ButtonRole.RejectRole)
            decision.setDefaultButton(save_button)
            decision.exec()
            if decision.clickedButton() == save_button:
                snapshot_path = next_snapshot_path(result.text, result.source)
                saved_path = save_plate_snapshot(result.plate_crop, snapshot_path)
                saved_snapshot = str(saved_path or "")

        result.snapshot_path = saved_snapshot
        append_plate_log(
            result.text,
            source=result.source,
            confidence=result.confidence,
            snapshot_path=None if not saved_snapshot else Path(saved_snapshot),
            watchlist_hit=result.watchlist_hit,
        )
        self._log_panel.add_results([result])
        self._camera_status[camera_index] = (
            f"Snapshot saved for {result.text}"
            if saved_snapshot
            else f"Skipped snapshot for {result.text}"
        )
        self._update_status_text()

        self._review_in_progress = False
        if self._pending_results:
            self._process_pending_results()
        else:
            self._set_pipeline_pause(False)

    def _update_status_text(self):
        if len(self._registered_cameras) == 0:
            self._status_label.setText(
                "No cameras registered - Save local or IP/RTSP cameras in Settings"
            )
            return
        if self._active_camera is not None:
            status = self._camera_status.get(int(self._active_camera), "Idle")
            source_label = self._source_labels.get(
                int(self._active_camera), f"CAM {self._active_camera}"
            )
            self._status_label.setText(
                f"Active: {len(self._registered_cameras)} camera(s) | Detection: {'Running' if self._running else 'Stopped'} | Viewing {source_label} | {status}"
            )
        else:
            self._status_label.setText(
                f"Active: {len(self._registered_cameras)} camera(s) | Detection: {'Running' if self._running else 'Stopped'}"
            )

    def closeEvent(self, event):
        self._stop_all_pipelines()
        super().closeEvent(event)

    def _on_clear_log(self):
        clear_plate_log()
        self._log_panel.clear()
