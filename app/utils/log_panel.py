"""
On-screen log panel.

Displays PlateResult entries in a scrollable list.
Deduplicates: same plate text within _DEDUP_WINDOW_SEC is not logged twice.
"""

from __future__ import annotations

import time
from collections import deque

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QDateTime

from app.detection.plate_pipeline import PlateResult


class LogEntry(QWidget):
    def __init__(self, result: PlateResult, parent=None):
        super().__init__(parent)
        self.setObjectName("logEntry")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        ts = QDateTime.fromSecsSinceEpoch(int(result.timestamp)).toString("hh:mm:ss")
        time_label = QLabel(ts)
        time_label.setObjectName("logTime")
        time_label.setFixedWidth(55)
        layout.addWidget(time_label)

        cam_label = QLabel(f"CAM {result.camera_index}")
        cam_label.setObjectName("logCam")
        cam_label.setFixedWidth(44)
        layout.addWidget(cam_label)

        plate_label = QLabel(result.text)
        plate_label.setObjectName("logPlate")
        plate_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(plate_label)

        conf_label = QLabel(f"{result.confidence:.0%}")
        conf_label.setObjectName("logConf")
        conf_label.setFixedWidth(38)
        conf_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(conf_label)


class LogPanel(QWidget):
    """
    Scrollable log of detected plates.
    """

    _DEDUP_WINDOW_SEC = 3.0
    _MAX_ENTRIES = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")
        self._recent: deque[tuple[str, float]] = deque(maxlen=100)
        self._entry_count = 0
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        header = QWidget()
        header.setObjectName("logHeader")
        header.setFixedHeight(40)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("DETECTIONS")
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

        # column headers
        col_header = QWidget()
        col_header.setObjectName("logColHeader")
        col_header.setFixedHeight(28)
        col_layout = QHBoxLayout(col_header)
        col_layout.setContentsMargins(12, 0, 12, 0)
        col_layout.setSpacing(12)

        for text, width, align in [
            ("TIME", 55, Qt.AlignmentFlag.AlignLeft),
            ("SRC", 44, Qt.AlignmentFlag.AlignLeft),
            ("PLATE TEXT", 0, Qt.AlignmentFlag.AlignLeft),
            ("CONF", 38, Qt.AlignmentFlag.AlignRight),
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

        # scroll area
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

        for result in results:
            if self._is_duplicate(result.text, now):
                continue

            self._recent.append((result.text, now))
            entry = LogEntry(result)

            # insert before the stretch at the bottom
            self._list_layout.insertWidget(self._list_layout.count() - 1, entry)
            added += 1
            self._entry_count += 1

            # trim if over max
            if self._entry_count > self._MAX_ENTRIES:
                item = self._list_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()
                    self._entry_count -= 1

        if added:
            self._count_label.setText(str(self._entry_count))
            # auto-scroll to bottom
            sb = self._scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._entry_count = 0
        self._count_label.setText("0")
        self._recent.clear()

    def _is_duplicate(self, text: str, now: float) -> bool:
        for prev_text, prev_time in self._recent:
            if prev_text == text and (now - prev_time) < self._DEDUP_WINDOW_SEC:
                return True
        return False
