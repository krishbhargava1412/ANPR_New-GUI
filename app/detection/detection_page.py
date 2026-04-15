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
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtCore import QSize, Qt, pyqtSlot
from PyQt6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.detection.plate_pipeline import DetectedBox, PlatePipeline, PlateResult
from app.detection.legacy_backend import append_plate_log, next_snapshot_path, save_plate_snapshot
from app.services.app_runtime import clear_plate_log, get_output_video_dir, load_ui_settings
from app.utils.log_panel import LogPanel


class BoxState(enum.Enum):
    SCANNING = "scanning"
    CONFIRMED = "confirmed"


_COLOR_SCANNING = (0, 200, 255)
_COLOR_CONFIRMED = (0, 230, 0)
_COLOR_LOW = (0, 208, 255)
_COLOR_ALERT = (32, 32, 255)
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.55
_FONT_THICKNESS = 1


class _BoxEntry:
    __slots__ = (
        "bbox",
        "confidence",
        "state",
        "text",
        "confirmed_at",
        "updated_at",
        "watchlist_hit",
    )

    def __init__(self, bbox: tuple[int, int, int, int], confidence: float):
        self.bbox = bbox
        self.confidence = confidence
        self.state = BoxState.SCANNING
        self.text = ""
        self.confirmed_at: float | None = None
        self.updated_at = time.monotonic()
        self.watchlist_hit = False

    def confirm(self, text: str, watchlist_hit: bool = False):
        self.text = text
        self.state = BoxState.CONFIRMED
        self.confirmed_at = time.monotonic()
        self.updated_at = time.monotonic()
        self.watchlist_hit = watchlist_hit

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


def _frame_to_pixmap(frame: np.ndarray, target_size: QSize) -> QPixmap:
    h, w, ch = frame.shape
    qt_img = QImage(frame.data, w, h, ch * w, QImage.Format.Format_BGR888)
    pixmap = QPixmap.fromImage(qt_img)
    return pixmap.scaled(
        target_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


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
        self._last_rendered_frame: np.ndarray | None = None

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
                self._entries[best_idx].confidence = result.confidence
                self._entries[best_idx].confirm(result.text, result.watchlist_hit)
            else:
                entry = _BoxEntry(result.bbox, result.confidence)
                entry.confirm(result.text, result.watchlist_hit)
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
        self._last_rendered_frame = annotated
        self.setPixmap(_frame_to_pixmap(annotated, self.size()))

    def _draw(self, frame: np.ndarray) -> np.ndarray:
        if not self._entries:
            return frame
        out = frame.copy()
        for entry in self._entries:
            x1, y1, x2, y2 = entry.bbox
            if entry.state is BoxState.SCANNING:
                color = _COLOR_SCANNING
                label = f"SCANNING | {entry.confidence:.2f}"
            else:
                if entry.watchlist_hit:
                    color = _COLOR_ALERT
                elif entry.confidence < 0.75:
                    color = _COLOR_LOW
                else:
                    color = _COLOR_CONFIRMED
                label = f"{entry.text} | {entry.confidence:.2f}"

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

    def rendered_frame(self) -> np.ndarray | None:
        return None if self._last_rendered_frame is None else self._last_rendered_frame.copy()


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
        self._grid_mode = 1
        self._running = False
        self._paused = False
        self._review_in_progress = False
        self._pending_results: list[PlateResult] = []
        self._latest_result_by_camera: dict[int, PlateResult] = {}
        self._stream_results: list[PlateResult] = []
        self._frame_skip = int(load_ui_settings()["frame_skip"])
        self._camera_last_frame_ts: dict[int, float] = {}
        self._camera_fps: dict[int, float] = {}
        self._camera_latency_ms: dict[int, float] = {}
        self._recording = False
        self._record_camera: int | None = None
        self._record_writer: cv2.VideoWriter | None = None
        self._selected_stream_result: PlateResult | None = None
        self._build_ui()
        self._bind_shortcuts()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 24)
        root.setSpacing(0)

        header_row = QHBoxLayout()
        title = QLabel("License Plate Detection")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Live multi-camera command center with overlays, alerts, and investigation context"
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
        root.addSpacing(14)

        self._alert_banner = QLabel("NO ACTIVE ALERTS")
        self._alert_banner.setObjectName("alertBanner")
        self._alert_banner.setProperty("state", "idle")
        self._alert_banner.setMinimumHeight(42)
        self._alert_banner.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self._alert_banner)
        root.addSpacing(14)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)

        self._start_btn = QPushButton("START DETECTION")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_btn.clicked.connect(self._toggle_detection)
        self._start_btn.setEnabled(False)
        ctrl.addWidget(self._start_btn)

        self._pause_btn = QPushButton("PAUSE")
        self._pause_btn.setObjectName("secondaryButton")
        self._pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._pause_btn.setEnabled(False)
        ctrl.addWidget(self._pause_btn)

        self._snapshot_btn = QPushButton("SNAPSHOT")
        self._snapshot_btn.setObjectName("secondaryButton")
        self._snapshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._snapshot_btn.clicked.connect(self._capture_snapshot)
        self._snapshot_btn.setEnabled(False)
        ctrl.addWidget(self._snapshot_btn)

        self._record_btn = QPushButton("RECORD OFF")
        self._record_btn.setObjectName("secondaryButton")
        self._record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._record_btn.clicked.connect(self._toggle_recording)
        self._record_btn.setEnabled(False)
        ctrl.addWidget(self._record_btn)

        self._camera_combo = QComboBox()
        self._camera_combo.setObjectName("cameraCombo")
        self._camera_combo.setMinimumWidth(220)
        self._camera_combo.currentIndexChanged.connect(self._on_camera_selected)
        ctrl.addWidget(self._camera_combo)

        grid_wrap = QWidget()
        grid_layout = QHBoxLayout(grid_wrap)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)
        grid_label = QLabel("GRID")
        grid_label.setObjectName("pageSubtitle")
        grid_layout.addWidget(grid_label)
        self._grid_group = QButtonGroup(self)
        self._grid_group.setExclusive(True)
        for mode in (1, 2, 3):
            btn = QPushButton(f"{mode}x{mode}")
            btn.setCheckable(True)
            btn.setObjectName("gridToggle")
            if mode == 1:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, current=mode: self._set_grid_mode(current))
            self._grid_group.addButton(btn, mode)
            grid_layout.addWidget(btn)
        ctrl.addWidget(grid_wrap)

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

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        self._feed_mode_label = QLabel("PRIMARY VIEW")
        self._feed_mode_label.setObjectName("sectionLabel")
        left_layout.addWidget(self._feed_mode_label)

        self._feed = FeedWidget()
        left_layout.addWidget(self._feed, stretch=1)

        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(10)
        meta_grid.setVerticalSpacing(10)
        self._meta_labels: dict[str, QLabel] = {}
        for index, key in enumerate(("camera", "fps", "latency", "overlay", "operator")):
            card = QFrame()
            card.setObjectName("monitorMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)
            title_label = QLabel(key.upper())
            title_label.setObjectName("metricLabel")
            value_label = QLabel("--")
            value_label.setObjectName("metricValue")
            value_label.setWordWrap(True)
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            self._meta_labels[key] = value_label
            meta_grid.addWidget(card, index // 3, index % 3)
        left_layout.addLayout(meta_grid)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self._log_panel.setMinimumWidth(320)
        self._log_panel.result_selected.connect(self._select_stream_result)
        self._log_panel.result_hovered.connect(self._preview_stream_result)
        right_layout.addWidget(self._log_panel, stretch=3)

        preview_card = QFrame()
        preview_card.setObjectName("monitorPanel")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(10)

        preview_title = QLabel("ACTIVE EVIDENCE REVIEW")
        preview_title.setObjectName("panelTitle")
        preview_layout.addWidget(preview_title)

        self._stream_preview = QLabel("Select or hover a live detection to preview evidence.")
        self._stream_preview.setObjectName("dropZone")
        self._stream_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stream_preview.setMinimumHeight(220)
        preview_layout.addWidget(self._stream_preview)

        self._stream_details = QLabel("Bounding box, confidence, and source context will appear here.")
        self._stream_details.setObjectName("pageSubtitle")
        self._stream_details.setWordWrap(True)
        preview_layout.addWidget(self._stream_details)

        self._stream_table = QTableWidget(0, 4)
        self._stream_table.setHorizontalHeaderLabels(["TIME", "PLATE", "CAMERA", "STATE"])
        self._stream_table.horizontalHeader().setStretchLastSection(True)
        self._stream_table.verticalHeader().setVisible(False)
        self._stream_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._stream_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._stream_table.itemSelectionChanged.connect(self._select_result_from_table)
        preview_layout.addWidget(self._stream_table)

        right_layout.addWidget(preview_card, stretch=2)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

    def _bind_shortcuts(self):
        QShortcut(QKeySequence("Space"), self, activated=self._toggle_detection)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self._toggle_pause)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._capture_snapshot)

    def _set_grid_mode(self, mode: int):
        self._grid_mode = mode
        self._refresh_feed()

    def _refresh_feed(self):
        if self._grid_mode == 1:
            self._feed_mode_label.setText("PRIMARY VIEW")
            self._restore_selected_camera_state()
            return

        grid_frame = self._compose_grid_frame()
        self._feed.clear_boxes()
        if grid_frame is None:
            self._feed.setText("NO FEED\n\nNo frames available for multi-camera grid view")
            self._feed.setPixmap(QPixmap())
            return
        self._feed_mode_label.setText(f"{self._grid_mode}x{self._grid_mode} SURVEILLANCE GRID")
        self._feed.update_frame(grid_frame)

    def _compose_grid_frame(self) -> np.ndarray | None:
        max_tiles = self._grid_mode * self._grid_mode
        camera_ids = self._registered_cameras[:max_tiles]
        frames: list[np.ndarray] = []
        tile_width = 480
        tile_height = 270
        for camera_index in camera_ids:
            frame = self._annotated_frame_for_camera(camera_index)
            if frame is None:
                blank = np.zeros((tile_height, tile_width, 3), dtype=np.uint8)
                cv2.putText(
                    blank,
                    self._source_labels.get(camera_index, f"CAM {camera_index}"),
                    (16, 32),
                    _FONT,
                    0.8,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                frame = blank
            resized = cv2.resize(frame, (tile_width, tile_height))
            cv2.putText(
                resized,
                self._source_labels.get(camera_index, f"CAM {camera_index}"),
                (14, 26),
                _FONT,
                0.65,
                (240, 240, 240),
                2,
                cv2.LINE_AA,
            )
            frames.append(resized)

        if not frames:
            return None

        while len(frames) < max_tiles:
            frames.append(np.zeros((tile_height, tile_width, 3), dtype=np.uint8))

        rows = []
        for start in range(0, len(frames), self._grid_mode):
            rows.append(np.hstack(frames[start : start + self._grid_mode]))
        return np.vstack(rows)

    def _annotated_frame_for_camera(self, camera_index: int) -> np.ndarray | None:
        frame = self._latest_frames.get(camera_index)
        if frame is None:
            return None
        out = frame.copy()
        for box in self._last_boxes.get(camera_index, []):
            x1, y1, x2, y2 = box.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), _COLOR_SCANNING, 2)
        for result in self._last_results.get(camera_index, []):
            x1, y1, x2, y2 = result.bbox
            color = _COLOR_ALERT if result.watchlist_hit else _COLOR_CONFIRMED
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            label = f"{result.text} | {result.confidence:.2f}"
            (tw, th), _ = cv2.getTextSize(label, _FONT, 0.55, 1)
            bg_y1 = max(0, y1 - th - 8)
            cv2.rectangle(out, (x1, bg_y1), (x1 + tw + 8, y1), color, -1)
            cv2.putText(out, label, (x1 + 4, y1 - 4), _FONT, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        return out

    def _render_evidence_snapshot(self, result: PlateResult) -> QPixmap | None:
        source_frame = self._annotated_frame_for_camera(result.camera_index)
        if source_frame is None:
            return None
        return _frame_to_pixmap(source_frame, self._stream_preview.size())

    def _select_stream_result(self, result: PlateResult):
        self._selected_stream_result = result
        self._log_panel.set_selected_result(result)
        self._populate_stream_preview(result)
        self._sync_stream_table_selection(result)
        camera_index = result.camera_index
        if self._active_camera != camera_index:
            combo_index = self._camera_combo.findData(camera_index)
            if combo_index >= 0:
                self._camera_combo.setCurrentIndex(combo_index)

    def _preview_stream_result(self, result: PlateResult):
        self._populate_stream_preview(result, preview_only=True)

    def _populate_stream_preview(self, result: PlateResult, preview_only: bool = False):
        pixmap = self._render_evidence_snapshot(result)
        if pixmap is not None:
            self._stream_preview.setPixmap(pixmap)
            self._stream_preview.setText("")
        else:
            self._stream_preview.setPixmap(QPixmap())
            self._stream_preview.setText("Evidence frame unavailable")

        severity = "WATCHLIST HIT" if result.watchlist_hit else "CLEAR"
        self._stream_details.setText(
            f"Plate: {result.text}\n"
            f"Confidence: {result.confidence:.2f}\n"
            f"Camera: {result.source or f'CAM {result.camera_index}'}\n"
            f"Tracking ID: CAM-{result.camera_index}-{int(result.timestamp)}\n"
            f"State: {severity}"
            + ("\nPreview only" if preview_only else "\nClick any live row to jump to frame")
        )

    def _sync_stream_table_selection(self, result: PlateResult):
        self._stream_table.blockSignals(True)
        for row in range(self._stream_table.rowCount()):
            item = self._stream_table.item(row, 0)
            if not item:
                continue
            payload = item.data(Qt.ItemDataRole.UserRole)
            if payload and payload.timestamp == result.timestamp and payload.text == result.text:
                self._stream_table.selectRow(row)
                break
        self._stream_table.blockSignals(False)

    def _select_result_from_table(self):
        items = self._stream_table.selectedItems()
        if not items:
            return
        result = items[0].data(Qt.ItemDataRole.UserRole)
        if result is not None:
            self._select_stream_result(result)

    def _refresh_stream_table(self):
        self._stream_table.setRowCount(len(self._stream_results[:20]))
        for row, result in enumerate(self._stream_results[:20]):
            state = "ALERT" if result.watchlist_hit else "TRACK"
            values = [
                datetime.fromtimestamp(result.timestamp).strftime("%H:%M:%S"),
                result.text,
                result.source or f"CAM {result.camera_index}",
                state,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, result)
                self._stream_table.setItem(row, column, item)
                if row == 0:
                    item.setBackground(Qt.GlobalColor.darkGreen)
                elif result.watchlist_hit:
                    item.setBackground(Qt.GlobalColor.darkRed)

    def _update_meta_cards(self):
        if self._active_camera is None:
            for label in self._meta_labels.values():
                label.setText("--")
            return
        camera_index = int(self._active_camera)
        active_result = self._latest_result_by_camera.get(camera_index)
        overlay_text = "Bounding boxes active"
        if active_result is not None:
            overlay_text = f"{active_result.text} @ {active_result.confidence:.2f}"
        self._meta_labels["camera"].setText(self._source_labels.get(camera_index, f"CAM {camera_index}"))
        self._meta_labels["fps"].setText(f"{self._camera_fps.get(camera_index, 0.0):.1f} FPS")
        self._meta_labels["latency"].setText(f"{self._camera_latency_ms.get(camera_index, 0.0):.0f} ms")
        self._meta_labels["overlay"].setText(overlay_text)
        self._meta_labels["operator"].setText(
            "Grid watch" if self._grid_mode > 1 else "Focused review"
        )

    def _raise_alert_banner(self, result: PlateResult):
        if result.watchlist_hit:
            self._alert_banner.setProperty("state", "alert")
            self._alert_banner.setText(
                f"WATCHLIST ALERT | {result.text} on {result.source or f'CAM {result.camera_index}'} | confidence {result.confidence:.2f}"
            )
            settings = load_ui_settings()
            if bool(settings.get("sound_alerts_enabled", True)):
                QApplication.beep()
        else:
            self._alert_banner.setProperty("state", "tracking")
            self._alert_banner.setText(
                f"LIVE TRACK | {result.text} | {result.source or f'CAM {result.camera_index}'} | click stream rows to jump"
            )
        self._alert_banner.style().unpolish(self._alert_banner)
        self._alert_banner.style().polish(self._alert_banner)
        self._alert_banner.update()

    def register_camera(self, index: int, label: str | None = None):
        if index in self._registered_cameras:
            if label:
                self._source_labels[index] = label
                self._refresh_camera_selector()
            return
        self._registered_cameras.append(index)
        self._source_labels[index] = label or f"CAM {index}"
        self._camera_status[index] = "Idle"
        self._start_btn.setEnabled(True)
        self._snapshot_btn.setEnabled(True)
        self._record_btn.setEnabled(self._running)
        self._refresh_camera_selector()
        if self._active_camera is None:
            self._active_camera = index
            self._camera_combo.setCurrentIndex(self._camera_combo.findData(index))
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
        self._camera_last_frame_ts.pop(index, None)
        self._camera_fps.pop(index, None)
        self._camera_latency_ms.pop(index, None)
        if index in self._registered_cameras:
            self._registered_cameras.remove(index)
        self._refresh_camera_selector()
        if self._active_camera == index:
            self._active_camera = (
                self._registered_cameras[0] if self._registered_cameras else None
            )
            if self._active_camera is not None:
                combo_idx = self._camera_combo.findData(self._active_camera)
                if combo_idx >= 0:
                    self._camera_combo.setCurrentIndex(combo_idx)
            self._restore_selected_camera_state()
        self._start_btn.setEnabled(len(self._registered_cameras) > 0)
        self._pause_btn.setEnabled(self._running and len(self._registered_cameras) > 0)
        self._snapshot_btn.setEnabled(len(self._registered_cameras) > 0)
        self._record_btn.setEnabled(self._running and len(self._registered_cameras) > 0)
        self._update_status_text()

    def _refresh_camera_selector(self):
        current = self._active_camera
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        for index in self._registered_cameras:
            status = self._camera_status.get(index, "Idle").lower()
            indicator = "●" if "scan" in status or "ready" in status or self._running else "○"
            state = "LIVE" if indicator == "●" else "OFFLINE"
            self._camera_combo.addItem(f"{self._source_labels.get(index, f'CAM {index}')} {indicator} {state}", index)
        if current is not None:
            combo_index = self._camera_combo.findData(current)
            if combo_index >= 0:
                self._camera_combo.setCurrentIndex(combo_index)
        self._camera_combo.blockSignals(False)

    @pyqtSlot(int, np.ndarray)
    def on_frame_ready(self, camera_index: int, frame: np.ndarray):
        now = time.monotonic()
        previous = self._camera_last_frame_ts.get(camera_index)
        if previous is not None:
            inst_fps = 1.0 / max(now - previous, 1e-3)
            current = self._camera_fps.get(camera_index, inst_fps)
            self._camera_fps[camera_index] = (current * 0.7) + (inst_fps * 0.3)
        self._camera_last_frame_ts[camera_index] = now
        self._latest_frames[camera_index] = frame.copy()
        if camera_index == self._active_camera or self._grid_mode > 1:
            self._refresh_feed()
            self._update_meta_cards()
            if self._recording and self._record_camera == camera_index and self._record_writer:
                recorded_frame = self._annotated_frame_for_camera(camera_index)
                self._record_writer.write(recorded_frame if recorded_frame is not None else frame)
        if not self._running:
            return
        if self._paused:
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

    def _toggle_pause(self):
        if not self._running:
            return
        self._paused = not self._paused
        self._set_pipeline_pause(self._paused)
        self._pause_btn.setText("RESUME" if self._paused else "PAUSE")
        self._update_status_text()

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
        self._paused = False
        for camera_index in self._registered_cameras:
            self._start_pipeline_for_camera(camera_index)
        self._start_btn.setText("STOP DETECTION")
        self._pause_btn.setEnabled(True)
        self._pause_btn.setText("PAUSE")
        self._record_btn.setEnabled(True)
        self._update_status_text()

    def _stop_all_pipelines(self):
        for camera_index in list(self._pipelines):
            self._stop_pipeline_for_camera(camera_index)
        self._running = False
        self._paused = False
        self._pending_results.clear()
        self._review_in_progress = False
        self._feed.clear_boxes()
        self._stop_recording()
        self._alert_banner.setProperty("state", "idle")
        self._alert_banner.setText("NO ACTIVE ALERTS")
        self._start_btn.setText("START DETECTION")
        self._pause_btn.setEnabled(False)
        self._pause_btn.setText("PAUSE")
        self._record_btn.setEnabled(False)
        self._refresh_camera_selector()
        self._update_status_text()

    def _start_pipeline_for_camera(self, camera_index: int):
        if camera_index in self._pipelines:
            return
        pipeline = PlatePipeline()
        pipeline.boxes_detected.connect(self._on_boxes_detected)
        pipeline.result_ready.connect(self._on_results)
        pipeline.telemetry.connect(self._on_pipeline_telemetry)
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
        camera_index = self._camera_combo.currentData()
        if camera_index is None:
            return
        self._active_camera = int(camera_index)
        self._restore_selected_camera_state()
        self._update_status_text()

    def _restore_selected_camera_state(self):
        if self._active_camera is None:
            self._feed.clear_boxes()
            self._feed.setText("NO FEED\n\nSave local or IP/RTSP cameras in Settings")
            return
        if self._grid_mode > 1:
            self._refresh_feed()
            return
        boxes = self._last_boxes.get(self._active_camera, [])
        results = self._last_results.get(self._active_camera, [])
        self._feed.set_scanning(boxes)
        self._feed.set_confirmed(results)
        frame = self._latest_frames.get(self._active_camera)
        if frame is not None:
            self._feed.update_frame(frame)
        self._update_meta_cards()

    @pyqtSlot(int, list)
    def _on_boxes_detected(self, camera_index: int, boxes: list[DetectedBox]):
        self._last_boxes[camera_index] = boxes
        if camera_index == self._active_camera or self._grid_mode > 1:
            self._refresh_feed()
        self._camera_status[camera_index] = f"Scanning {len(boxes)} plate(s)"
        self._refresh_camera_selector()
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
        self._refresh_camera_selector()
        self._update_status_text()

    @pyqtSlot(int, dict)
    def _on_pipeline_telemetry(self, camera_index: int, payload: dict):
        self._camera_latency_ms[camera_index] = float(payload.get("latency_ms", 0.0))
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
        self._latest_result_by_camera[camera_index] = result
        if camera_index == self._active_camera:
            self._refresh_feed()

        saved_snapshot = ""
        if bool(load_ui_settings().get("save_snapshots", True)):
            snapshot_path = next_snapshot_path(result.text, result.source)
            frame_to_save = self._annotated_frame_for_camera(camera_index)
            if frame_to_save is None and result.plate_crop is not None:
                frame_to_save = result.plate_crop
            saved_path = save_plate_snapshot(frame_to_save, snapshot_path) if frame_to_save is not None else None
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
        self._stream_results.insert(0, result)
        self._stream_results = self._stream_results[:50]
        self._refresh_stream_table()
        self._select_stream_result(result)
        self._raise_alert_banner(result)
        self._camera_status[camera_index] = (
            f"Snapshot saved for {result.text}"
            if saved_snapshot
            else f"Logged {result.text}"
        )
        self._update_status_text()

        self._review_in_progress = False
        if self._pending_results:
            self._process_pending_results()
        else:
            self._set_pipeline_pause(False)

    def _capture_snapshot(self):
        if self._active_camera is None:
            return
        frame = self._annotated_frame_for_camera(self._active_camera)
        if frame is None:
            frame = self._latest_frames.get(self._active_camera)
        if frame is None:
            return
        source = self._source_labels.get(self._active_camera, f"CAM {self._active_camera}")
        snapshot_path = next_snapshot_path("manual", source)
        saved_path = save_plate_snapshot(frame, snapshot_path)
        if saved_path:
            self._camera_status[self._active_camera] = f"Snapshot saved: {saved_path.name}"
            self._update_status_text()

    def _toggle_recording(self):
        if not self._running:
            return
        if self._recording:
            self._stop_recording()
            self._update_status_text()
            return
        if self._active_camera is None:
            return
        frame = self._latest_frames.get(self._active_camera)
        if frame is None:
            return
        output_video_dir = get_output_video_dir()
        output_video_dir.mkdir(parents=True, exist_ok=True)
        filename = f"cam_{self._active_camera}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        path = output_video_dir / filename
        height, width = frame.shape[:2]
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            max(self._camera_fps.get(self._active_camera, 10.0), 10.0),
            (width, height),
        )
        if not writer.isOpened():
            return
        self._recording = True
        self._record_camera = self._active_camera
        self._record_writer = writer
        self._record_btn.setText("RECORD ON")
        self._camera_status[self._active_camera] = f"Recording to {filename}"
        self._update_status_text()

    def _stop_recording(self):
        if self._record_writer is not None:
            self._record_writer.release()
        self._record_writer = None
        self._record_camera = None
        self._recording = False
        self._record_btn.setText("RECORD OFF")

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
            fps = self._camera_fps.get(int(self._active_camera), 0.0)
            latency = self._camera_latency_ms.get(int(self._active_camera), 0.0)
            self._status_label.setText(
                f"Active: {len(self._registered_cameras)} camera(s) | Detection: "
                f"{'Paused' if self._paused else 'Running' if self._running else 'Stopped'} | "
                f"Viewing {source_label} | {fps:.1f} FPS | {latency:.0f} ms | Overlay live | {status}"
            )
        else:
            self._status_label.setText(
                f"Active: {len(self._registered_cameras)} camera(s) | Detection: "
                f"{'Paused' if self._paused else 'Running' if self._running else 'Stopped'}"
            )

    def closeEvent(self, event):
        self._stop_all_pipelines()
        super().closeEvent(event)

    def _on_clear_log(self):
        clear_plate_log()
        self._log_panel.clear()
        self._stream_results.clear()
        self._stream_table.setRowCount(0)
