"""
On-screen log panel.

Displays PlateResult entries in a scrollable list with selection support for
the operator workflow.
"""

from __future__ import annotations

import time
from collections import deque

from PyQt6.QtCore import QDateTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.detection.plate_pipeline import PlateResult


class LogEntry(QFrame):
    selected = pyqtSignal(object)
    hovered = pyqtSignal(object)

    def __init__(self, result: PlateResult, parent=None):
        super().__init__(parent)
        self.result = result
        self.setObjectName("logEntry")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)
        if result.watchlist_hit:
            self.setProperty("severity", "alert")
        elif result.confidence < 0.75:
            self.setProperty("severity", "warning")
        else:
            self.setProperty("severity", "normal")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        ts = QDateTime.fromSecsSinceEpoch(int(result.timestamp)).toString("hh:mm:ss")
        time_label = QLabel(ts)
        time_label.setObjectName("logTime")
        time_label.setFixedWidth(62)
        layout.addWidget(time_label)

        cam_label = QLabel(result.source or f"CAM {result.camera_index}")
        cam_label.setObjectName("logCam")
        cam_label.setFixedWidth(78)
        cam_label.setWordWrap(True)
        layout.addWidget(cam_label)

        plate_label = QLabel(result.text)
        plate_label.setObjectName("logPlate")
        plate_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(plate_label)

        conf_label = QLabel(f"{result.confidence:.0%}")
        conf_label.setObjectName("logConf")
        conf_label.setFixedWidth(42)
        conf_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(conf_label)

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.result)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.hovered.emit(self.result)
        super().enterEvent(event)


class LogPanel(QWidget):
    _DEDUP_WINDOW_SEC = 3.0
    _MAX_ENTRIES = 200

    result_selected = pyqtSignal(object)
    result_hovered = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")
        self._recent: deque[tuple[str, float]] = deque(maxlen=100)
        self._entry_count = 0
        self._entries: list[LogEntry] = []
        self._selected_entry: LogEntry | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("logHeader")
        header.setFixedHeight(40)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("LIVE DETECTION STREAM")
        title.setObjectName("logHeaderTitle")
        h_layout.addWidget(title)

        self._count_label = QLabel("0")
        self._count_label.setObjectName("logCount")
        h_layout.addWidget(self._count_label)
        h_layout.addStretch()

        clear_btn = QPushButton("CLEAR")
        clear_btn.setObjectName("logClearButton")
        clear_btn.setFixedHeight(22)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self.clear)
        h_layout.addWidget(clear_btn)
        root.addWidget(header)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)

        col_header = QWidget()
        col_header.setObjectName("logColHeader")
        col_header.setFixedHeight(28)
        col_layout = QHBoxLayout(col_header)
        col_layout.setContentsMargins(12, 0, 12, 0)
        col_layout.setSpacing(12)

        for text, width, align in [
            ("TIME", 62, Qt.AlignmentFlag.AlignLeft),
            ("SRC", 78, Qt.AlignmentFlag.AlignLeft),
            ("PLATE", 0, Qt.AlignmentFlag.AlignLeft),
            ("CONF", 42, Qt.AlignmentFlag.AlignRight),
        ]:
            lbl = QLabel(text)
            lbl.setObjectName("logColLabel")
            if width:
                lbl.setFixedWidth(width)
            else:
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lbl.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
            col_layout.addWidget(lbl)

        root.addWidget(col_header)

        divider2 = QFrame()
        divider2.setObjectName("divider")
        divider2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider2)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("logScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_widget = QWidget()
        self._list_widget.setObjectName("logList")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(1)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll, stretch=1)

    def add_results(self, results: list[PlateResult]):
        now = time.time()
        added = 0
        newest_entry: LogEntry | None = None

        for result in results:
            if self._is_duplicate(result.text, now):
                continue

            self._recent.append((result.text, now))
            entry = LogEntry(result)
            entry.selected.connect(self._on_entry_selected)
            entry.hovered.connect(self.result_hovered.emit)
            self._list_layout.insertWidget(0, entry)
            self._entries.insert(0, entry)
            newest_entry = entry
            added += 1
            self._entry_count += 1

            if self._entry_count > self._MAX_ENTRIES:
                old_entry = self._entries.pop()
                self._list_layout.removeWidget(old_entry)
                old_entry.deleteLater()
                self._entry_count -= 1

        if added:
            self._count_label.setText(str(self._entry_count))
            if newest_entry is not None:
                self._on_entry_selected(newest_entry.result)
            sb = self._scroll.verticalScrollBar()
            sb.setValue(sb.minimum())

    def set_selected_result(self, result: PlateResult | None):
        matched_entry = None
        if result is not None:
            for entry in self._entries:
                if entry.result.timestamp == result.timestamp and entry.result.text == result.text:
                    matched_entry = entry
                    break
        self._selected_entry = matched_entry
        for entry in self._entries:
            entry.set_selected(entry is matched_entry)

    def clear(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._entries.clear()
        self._selected_entry = None
        self._entry_count = 0
        self._count_label.setText("0")
        self._recent.clear()

    def _on_entry_selected(self, result: PlateResult):
        self.result_selected.emit(result)
        self.set_selected_result(result)

    def _is_duplicate(self, text: str, now: float) -> bool:
        for prev_text, prev_time in self._recent:
            if prev_text == text and (now - prev_time) < self._DEDUP_WINDOW_SEC:
                return True
        return False
