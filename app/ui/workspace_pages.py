from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
)

from app.services.app_runtime import (
    APP_LOG_PATH,
    OUTPUTS_DIR,
    PLATE_LOG_PATH,
    SNAPSHOT_DIR,
    SETTINGS_PATH,
    WATCHLIST_PATH,
    dashboard_stats,
    dependency_status,
    load_ui_settings,
    open_in_shell,
    save_ui_settings,
    search_plate_log,
)


def _page_header(title: str, subtitle: str) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(4)
    t = QLabel(title)
    t.setObjectName("pageTitle")
    s = QLabel(subtitle)
    s.setObjectName("pageSubtitle")
    layout.addWidget(t)
    layout.addWidget(s)
    return layout


def _stat_card_widget(label: str) -> tuple[QWidget, QLabel]:
    card = QWidget()
    card.setObjectName("statCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(4)

    value_label = QLabel("0")
    value_label.setObjectName("statValue")
    layout.addWidget(value_label)

    text_label = QLabel(label)
    text_label.setObjectName("statLabel")
    layout.addWidget(text_label)
    return card, value_label


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._value_labels: dict[str, QLabel] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(24)
        layout.addLayout(_page_header("Dashboard", "Integrated ANPR runtime overview"))

        row = QHBoxLayout()
        row.setSpacing(12)
        for key, label in (
            ("detections", "DETECTIONS LOGGED"),
            ("plates", "UNIQUE PLATES"),
            ("snapshots", "SNAPSHOTS SAVED"),
            ("watchlist_hits", "WATCHLIST HITS"),
        ):
            card, value_label = _stat_card_widget(label)
            self._value_labels[key] = value_label
            row.addWidget(card)
        layout.addLayout(row)

        self._latest_label = QLabel("")
        self._latest_label.setObjectName("pageSubtitle")
        layout.addWidget(self._latest_label)

        actions = QHBoxLayout()
        for text, handler in (
            ("REFRESH", self.refresh),
            ("OPEN OUTPUTS", lambda: open_in_shell(OUTPUTS_DIR)),
            ("OPEN WATCHLIST", lambda: open_in_shell(WATCHLIST_PATH)),
            ("OPEN LOG CSV", lambda: open_in_shell(PLATE_LOG_PATH)),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)

        layout.addStretch()

    def refresh(self):
        stats = dashboard_stats()
        for key, label in self._value_labels.items():
            label.setText(stats.get(key, "0"))
        self._latest_label.setText(f"Latest detection: {stats['latest']}")


class PipelinePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(20)
        layout.addLayout(_page_header("Pipeline", "Check old batch-pipeline integration and runtime readiness"))

        self._status = QTextEdit()
        self._status.setReadOnly(True)
        self._status.setMinimumHeight(260)
        layout.addWidget(self._status)

        row = QHBoxLayout()
        for text, handler in (
            ("REFRESH CHECKS", self.refresh),
            ("OPEN OUTPUTS", lambda: open_in_shell(OUTPUTS_DIR)),
            ("OPEN LOG FOLDER", lambda: open_in_shell(PLATE_LOG_PATH.parent)),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def refresh(self):
        status = dependency_status()
        lines = [
            f"Batch detector: {status['pipeline_batch']}",
            f"CSV interpolation: {status['pipeline_interpolate']}",
            f"Video renderer: {status['pipeline_visualize']}",
            "",
            f"Detection model: {status['model_path']}",
            f"Model exists: {status['model_exists']}",
            f"Device: {status['device']}",
            f"Torch: {status['torch']}",
            f"OpenCV: {status['opencv']}",
            f"EasyOCR: {status['easyocr']}",
            f"Ultralytics: {status['ultralytics']}",
            "",
            "This page currently verifies pipeline integration readiness.",
            "The live multi-camera path is integrated in Cameras + Detection.",
        ]
        self._status.setPlainText("\n".join(lines))


class HistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("History", "Search detections, watchlist hits, and evidence snapshots"))

        filters = QHBoxLayout()
        self._plate_edit = QLineEdit()
        self._plate_edit.setPlaceholderText("Plate text")
        self._source_edit = QLineEdit()
        self._source_edit.setPlaceholderText("Source")
        self._from_edit = QLineEdit()
        self._from_edit.setPlaceholderText("From YYYY-MM-DD")
        self._to_edit = QLineEdit()
        self._to_edit.setPlaceholderText("To YYYY-MM-DD")
        self._watchlist_only = QCheckBox("Watchlist only")
        for widget in (self._plate_edit, self._source_edit, self._from_edit, self._to_edit, self._watchlist_only):
            filters.addWidget(widget)
        search_btn = QPushButton("SEARCH")
        search_btn.setObjectName("primaryButton")
        search_btn.clicked.connect(self.refresh)
        filters.addWidget(search_btn)
        layout.addLayout(filters)

        splitter_row = QHBoxLayout()

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Timestamp", "Plate", "Source", "Confidence", "Watchlist"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._update_preview)
        splitter_row.addWidget(self._table, stretch=3)

        side = QVBoxLayout()
        self._preview = QLabel("No snapshot selected")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(240, 180)
        self._preview.setObjectName("dropZone")
        side.addWidget(self._preview)

        self._details = QLabel("")
        self._details.setWordWrap(True)
        self._details.setObjectName("pageSubtitle")
        side.addWidget(self._details)

        for text, handler in (
            ("OPEN SNAPSHOT", self._open_selected_snapshot),
            ("OPEN SNAPSHOT FOLDER", lambda: open_in_shell(SNAPSHOT_DIR)),
            ("OPEN LOG CSV", lambda: open_in_shell(PLATE_LOG_PATH)),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            side.addWidget(btn)
        side.addStretch()
        splitter_row.addLayout(side, stretch=2)

        layout.addLayout(splitter_row)

    def refresh(self):
        matches = search_plate_log(
            self._plate_edit.text(),
            source_filter=self._source_edit.text(),
            watchlist_only=self._watchlist_only.isChecked(),
            from_date=self._from_edit.text().strip(),
            to_date=self._to_edit.text().strip(),
        )
        self._table.setRowCount(len(matches))
        for row_index, match in enumerate(matches):
            values = [
                match["timestamp"],
                match["plate"],
                match["source"],
                "" if match["confidence"] is None else f"{match['confidence']:.4f}",
                "WATCHLIST" if match["watchlist_hit"] else "Clear",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, match)
                self._table.setItem(row_index, column, item)
        if matches:
            self._table.selectRow(0)
        else:
            self._preview.setText("No snapshot selected")
            self._preview.setPixmap(QPixmap())
            self._details.setText("No matching detections.")

    def _selected_match(self) -> dict[str, object] | None:
        items = self._table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _update_preview(self):
        match = self._selected_match()
        if not match:
            return
        snapshot_path = Path(str(match.get("snapshot_path") or ""))
        self._details.setText(
            f"Plate: {match['plate']}\n"
            f"Source: {match['source']}\n"
            f"Time: {match['timestamp']}\n"
            f"Snapshot: {snapshot_path if snapshot_path else 'None'}"
        )
        if snapshot_path.exists():
            pixmap = QPixmap(str(snapshot_path))
            self._preview.setPixmap(pixmap.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self._preview.setText("")
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("Snapshot unavailable")

    def _open_selected_snapshot(self):
        match = self._selected_match()
        if not match:
            return
        snapshot_path = Path(str(match.get("snapshot_path") or ""))
        if snapshot_path.exists():
            open_in_shell(snapshot_path)


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(20)
        layout.addLayout(_page_header("Settings", "Detection, storage, and alert settings from the old workflow"))

        form_box = QGroupBox("Runtime")
        form = QFormLayout(form_box)
        form.setSpacing(12)

        self._confidence = QDoubleSpinBox()
        self._confidence.setRange(0.05, 1.0)
        self._confidence.setDecimals(2)
        self._confidence.setSingleStep(0.05)
        form.addRow("Confidence threshold", self._confidence)

        self._frame_skip = QSpinBox()
        self._frame_skip.setRange(1, 10)
        form.addRow("Frame skip", self._frame_skip)

        self._save_snapshots = QCheckBox("Save plate snapshots")
        form.addRow("Storage", self._save_snapshots)

        self._watchlist_alerts = QCheckBox("Enable watchlist alerts")
        form.addRow("Alerts", self._watchlist_alerts)

        layout.addWidget(form_box)

        path_box = QGroupBox("Paths")
        path_layout = QFormLayout(path_box)
        for label, path in (
            ("Settings", SETTINGS_PATH),
            ("Watchlist", WATCHLIST_PATH),
            ("Plate log", PLATE_LOG_PATH),
            ("Snapshots", SNAPSHOT_DIR),
        ):
            line = QLineEdit(str(path))
            line.setReadOnly(True)
            path_layout.addRow(label, line)
        layout.addWidget(path_box)

        row = QHBoxLayout()
        for text, handler in (
            ("SAVE SETTINGS", self._save),
            ("OPEN WATCHLIST", lambda: open_in_shell(WATCHLIST_PATH)),
            ("OPEN OUTPUTS", lambda: open_in_shell(OUTPUTS_DIR)),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton" if text != "SAVE SETTINGS" else "primaryButton")
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def _load(self):
        settings = load_ui_settings()
        self._confidence.setValue(float(settings["confidence_threshold"]))
        self._frame_skip.setValue(int(settings["frame_skip"]))
        self._save_snapshots.setChecked(bool(settings["save_snapshots"]))
        self._watchlist_alerts.setChecked(bool(settings["watchlist_alerts_enabled"]))

    def _save(self):
        settings = save_ui_settings(
            {
                "confidence_threshold": float(self._confidence.value()),
                "frame_skip": int(self._frame_skip.value()),
                "save_snapshots": bool(self._save_snapshots.isChecked()),
                "watchlist_alerts_enabled": bool(self._watchlist_alerts.isChecked()),
            }
        )
        self.settings_changed.emit(settings)


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(20)
        layout.addLayout(_page_header("About", "Diagnostics and integration checks for the old ANPR stack"))

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(10)
        layout.addLayout(self._grid)

        row = QHBoxLayout()
        for text, handler in (
            ("REFRESH", self.refresh),
            ("OPEN APP LOG", lambda: open_in_shell(APP_LOG_PATH)),
            ("OPEN OUTPUTS", lambda: open_in_shell(OUTPUTS_DIR)),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def refresh(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        status = dependency_status()
        for row_index, (label, value) in enumerate(status.items()):
            key = QLabel(label.replace("_", " ").upper())
            key.setObjectName("sectionLabel")
            val = QLabel(value)
            val.setWordWrap(True)
            val.setObjectName("pageSubtitle")
            self._grid.addWidget(key, row_index, 0)
            self._grid.addWidget(val, row_index, 1)

