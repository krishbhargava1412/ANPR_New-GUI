from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import cv2

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
    QMessageBox,
    QFileDialog,
    QComboBox,
    QSlider,
    QTabWidget,
    QHeaderView,
    QSizePolicy,
)

from app.services.app_runtime import (
    available_model_names,
    dashboard_stats,
    dependency_status,
    get_app_log_path,
    get_output_video_dir,
    get_outputs_dir,
    get_plate_log_runtime_path,
    get_settings_path,
    get_snapshot_dir,
    get_watchlist_runtime_path,
    grouped_plate_history,
    load_case_flags,
    load_ui_settings,
    recent_detections,
    save_ui_settings,
    save_case_flag,
    save_watchlist_entries,
    search_plate_log,
    watchlist_entries,
    clear_plate_log,
    clear_outputs,
    delete_history_entries,
    delete_snapshot_file,
)
from app.storage import load_storage_paths, save_storage_paths
from app.storage.database import AVAILABLE_USER_ROLES


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
        self._trend_labels: dict[str, QLabel] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(14)
        self._root_layout = layout
        layout.addLayout(_page_header("Dashboard", "Live surveillance overview, evidence triage, and system health"))

        ticker = QFrame()
        ticker.setObjectName("tickerBar")
        ticker_row = QHBoxLayout(ticker)
        ticker_row.setContentsMargins(16, 12, 16, 12)
        self._latest_label = QLabel("")
        self._latest_label.setObjectName("tickerLabel")
        ticker_row.addWidget(self._latest_label)
        ticker_row.addStretch()
        layout.addWidget(ticker)

        self._body_grid = QGridLayout()
        self._body_grid.setContentsMargins(0, 0, 0, 0)
        self._body_grid.setHorizontalSpacing(14)
        self._body_grid.setVerticalSpacing(14)

        left_panel = QWidget()
        self._left_panel = left_panel
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(14)

        evidence_card = QFrame()
        evidence_card.setObjectName("monitorPanel")
        evidence_layout = QVBoxLayout(evidence_card)
        evidence_layout.setContentsMargins(16, 16, 16, 16)
        evidence_layout.setSpacing(10)
        evidence_title = QLabel("LATEST DETECTION")
        evidence_title.setObjectName("panelTitle")
        evidence_layout.addWidget(evidence_title)

        self._preview = QLabel("No recent evidence")
        self._preview.setObjectName("dropZone")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(320)
        evidence_layout.addWidget(self._preview)

        evidence_meta = QGridLayout()
        evidence_meta.setHorizontalSpacing(12)
        evidence_meta.setVerticalSpacing(8)
        self._hero_labels = {}
        for idx, key in enumerate(("plate", "confidence", "timestamp", "source")):
            key_label = QLabel(key.upper())
            key_label.setObjectName("metricLabel")
            val = QLabel("--")
            val.setObjectName("metricValue")
            val.setWordWrap(True)
            self._hero_labels[key] = val
            evidence_meta.addWidget(key_label, idx, 0)
            evidence_meta.addWidget(val, idx, 1)
        evidence_layout.addLayout(evidence_meta)
        left.addWidget(evidence_card, stretch=3)
        self._evidence_card = evidence_card

        recent_card = QFrame()
        recent_card.setObjectName("monitorPanel")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(14, 14, 14, 14)
        recent_layout.setSpacing(8)
        recent_title = QLabel("RECENT DETECTIONS")
        recent_title.setObjectName("panelTitle")
        recent_layout.addWidget(recent_title)
        self._recent_table = QTableWidget(0, 4)
        self._recent_table.setHorizontalHeaderLabels(["TIME", "PLATE", "CAM", "STATE"])
        self._recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._recent_table.verticalHeader().setVisible(False)
        self._recent_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._recent_table.setMaximumHeight(220)
        self._recent_table.itemSelectionChanged.connect(self._update_preview)
        recent_layout.addWidget(self._recent_table)
        left.addWidget(recent_card, stretch=2)
        self._recent_card = recent_card

        right_panel = QWidget()
        self._right_panel = right_panel
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(14)

        metrics_card = QFrame()
        metrics_card.setObjectName("monitorPanel")
        metrics_layout = QGridLayout(metrics_card)
        metrics_layout.setContentsMargins(14, 14, 14, 14)
        metrics_layout.setHorizontalSpacing(10)
        metrics_layout.setVerticalSpacing(10)
        metric_items = (
            ("detections", "DETECTIONS"),
            ("plates", "UNIQUE PLATES"),
            ("rate_per_min", "PLATES / MIN"),
            ("active_cameras", "ACTIVE CAMERAS"),
            ("avg_confidence", "AVG CONFIDENCE"),
            ("watchlist_hits", "WATCHLIST HITS"),
        )
        for index, (key, label) in enumerate(metric_items):
            card, value_label = _stat_card_widget(label)
            self._value_labels[key] = value_label
            metrics_layout.addWidget(card, index // 2, index % 2)
        right.addWidget(metrics_card)
        self._metrics_card = metrics_card

        trend_card = QFrame()
        trend_card.setObjectName("monitorPanel")
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(14, 14, 14, 14)
        trend_layout.setSpacing(8)
        trend_title = QLabel("CAMERA STATUS + TRENDS")
        trend_title.setObjectName("panelTitle")
        trend_layout.addWidget(trend_title)
        for key in ("delta", "sparkline", "camera_status", "watchlist"):
            label = QLabel("--")
            label.setObjectName("pageSubtitle")
            label.setWordWrap(True)
            self._trend_labels[key] = label
            trend_layout.addWidget(label)
        self._trend_card = trend_card

        self._system_box = QGroupBox("Collapsed System Telemetry")
        self._system_box.setCheckable(True)
        self._system_box.setChecked(False)
        system_layout = QGridLayout(self._system_box)
        self._system_labels = {}
        for idx, (label, key) in enumerate(
            [
                ("Device", "device"),
                ("Model", "model_path"),
                ("GPU / Runtime", "torch"),
                ("OCR", "paddle"),
                ("Errors", "outputs"),
            ]
        ):
            key_label = QLabel(label)
            key_label.setObjectName("sectionLabel")
            value = QLabel("--")
            value.setObjectName("pageSubtitle")
            value.setWordWrap(True)
            self._system_labels[key] = value
            system_layout.addWidget(key_label, idx, 0)
            system_layout.addWidget(value, idx, 1)
        right.addStretch()
        self._body_grid.addWidget(left_panel, 0, 0)
        self._body_grid.addWidget(right_panel, 0, 1)
        self._body_grid.setColumnStretch(0, 1)
        self._body_grid.setColumnStretch(1, 0)
        layout.addLayout(self._body_grid, stretch=1)
        self._trend_card.hide()
        self._system_box.hide()
        self.apply_responsive_layout("medium", 1366)

    def refresh(self):
        stats = dashboard_stats()
        for key, label in self._value_labels.items():
            label.setText(stats.get(key, "0"))
        self._latest_label.setText(
            f"LIVE ACTIVITY STRIP  |  Last detection {stats['latest']}  |  "
            f"{stats.get('active_cameras', '0')} configured cameras  |  "
            f"Trend {stats.get('trend_delta', '+0 plates/min')}  |  "
            f"Sparkline {stats.get('sparkline', '0 0 0 0 0')}"
        )
        self._trend_labels["delta"].setText(
            f"Traffic trend: {stats.get('trend_delta', '+0 plates/min')}"
        )
        self._trend_labels["sparkline"].setText(
            f"Last 5 min: {stats.get('sparkline', '0 0 0 0 0')}"
        )
        self._trend_labels["camera_status"].setText(
            f"Camera readiness: {stats.get('active_cameras', '0')} configured | compact operator mode active"
        )
        self._trend_labels["watchlist"].setText(
            f"Watchlist pressure: {stats.get('watchlist_hits', '0')} total hit(s)"
        )

        runtime = dependency_status()
        for key, label in self._system_labels.items():
            label.setText(str(runtime.get(key, "--")))

        matches = recent_detections(12)
        self._recent_table.setRowCount(len(matches))
        for row_index, match in enumerate(matches):
            status = "WATCHLIST" if match["watchlist_hit"] else "CLEAR"
            values = [
                match["timestamp"].split(" ")[-1],
                match["plate"],
                match["source"],
                status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, match)
                self._recent_table.setItem(row_index, column, item)
                if match["watchlist_hit"]:
                    item.setBackground(Qt.GlobalColor.darkRed)
        if matches:
            self._recent_table.selectRow(0)
            self._populate_latest_detection(matches[0])
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("No recent evidence")
            for label in self._hero_labels.values():
                label.setText("--")

    def _clear_log(self):
        clear_plate_log()
        self.refresh()

    def _clear_outputs(self):
        clear_outputs()
        self.refresh()

    def _selected_dashboard_match(self) -> dict[str, object] | None:
        items = self._recent_table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _update_preview(self):
        match = self._selected_dashboard_match()
        if not match:
            return
        self._populate_latest_detection(match)

    def _populate_latest_detection(self, match: dict[str, object]):
        snapshot_path = Path(str(match.get("snapshot_path") or ""))
        self._hero_labels["plate"].setText(str(match["plate"]))
        self._hero_labels["confidence"].setText(
            "--" if match["confidence"] is None else f"{float(match['confidence']):.2f}"
        )
        self._hero_labels["timestamp"].setText(str(match["timestamp"]))
        self._hero_labels["source"].setText(str(match["source"]))
        if snapshot_path.exists():
            pixmap = QPixmap(str(snapshot_path))
            self._preview.setPixmap(
                pixmap.scaled(
                    self._preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._preview.setText("")
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("Snapshot unavailable")

    def apply_responsive_layout(self, breakpoint: str, window_width: int):
        margins = {
            "small": (16, 16, 16, 12),
            "medium": (22, 22, 22, 16),
            "large": (28, 28, 28, 24),
        }[breakpoint]
        self._root_layout.setContentsMargins(*margins)

        while self._body_grid.count():
            self._body_grid.takeAt(0)

        if breakpoint == "small":
            self._right_panel.setMaximumWidth(16777215)
            self._recent_table.setMaximumHeight(16777215)
            self._preview.setMinimumHeight(240)
            self._body_grid.addWidget(self._left_panel, 0, 0)
            self._body_grid.addWidget(self._right_panel, 1, 0)
            self._body_grid.setColumnStretch(0, 1)
            self._body_grid.setColumnStretch(1, 0)
        else:
            self._right_panel.setMaximumWidth(320 if breakpoint == "medium" else 360)
            self._recent_table.setMaximumHeight(220 if breakpoint == "medium" else 260)
            self._preview.setMinimumHeight(320 if breakpoint == "large" else 280)
            self._body_grid.addWidget(self._left_panel, 0, 0)
            self._body_grid.addWidget(self._right_panel, 0, 1)
            self._body_grid.setColumnStretch(0, 1)
            self._body_grid.setColumnStretch(1, 0)


class HistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._all_matches: list[dict[str, object]] = []
        self._grouped_matches: list[dict[str, object]] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(14)
        self._root_layout = layout
        layout.addLayout(
            _page_header(
                "History", "Investigation workflow grouped by plate, with timeline review and case notes"
            )
        )

        self._filters_widget = QWidget()
        self._filters_grid = QGridLayout(self._filters_widget)
        self._filters_grid.setContentsMargins(0, 0, 0, 0)
        self._filters_grid.setHorizontalSpacing(12)
        self._filters_grid.setVerticalSpacing(12)
        self._plate_edit = QLineEdit()
        self._plate_edit.setPlaceholderText("Plate text")
        self._source_edit = QLineEdit()
        self._source_edit.setPlaceholderText("Camera / source")
        self._time_preset = QComboBox()
        self._time_preset.addItems(["All Time", "Last 1 Hour", "Last 24 Hours", "Last 7 Days"])
        self._conf_min = QDoubleSpinBox()
        self._conf_min.setRange(0.0, 1.0)
        self._conf_min.setSingleStep(0.05)
        self._conf_min.setPrefix("Min ")
        self._conf_min.setValue(0.0)
        self._conf_max = QDoubleSpinBox()
        self._conf_max.setRange(0.0, 1.0)
        self._conf_max.setSingleStep(0.05)
        self._conf_max.setPrefix("Max ")
        self._conf_max.setValue(1.0)
        self._watchlist_only = QCheckBox("Watchlist only")
        for widget in (
            self._plate_edit,
            self._source_edit,
            self._time_preset,
            self._conf_min,
            self._conf_max,
            self._watchlist_only,
        ):
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._conf_min.hide()
        self._conf_max.hide()
        self._watchlist_only.hide()
        search_btn = QPushButton("SEARCH")
        search_btn.setObjectName("primaryButton")
        search_btn.clicked.connect(self.refresh)
        self._search_btn = search_btn
        layout.addWidget(self._filters_widget)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self._seen_count = _stat_card_widget("SIGHTINGS")
        self._first_seen = _stat_card_widget("FIRST SEEN")
        self._last_seen = _stat_card_widget("LAST SEEN")
        self._avg_conf = _stat_card_widget("AVG CONFIDENCE")
        for card, _ in (
            self._seen_count,
            self._first_seen,
            self._last_seen,
            self._avg_conf,
        ):
            summary_row.addWidget(card)
        layout.addLayout(summary_row)

        self._content_grid = QGridLayout()
        self._content_grid.setContentsMargins(0, 0, 0, 0)
        self._content_grid.setHorizontalSpacing(14)
        self._content_grid.setVerticalSpacing(14)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["PLATE", "SEEN", "FIRST", "LAST", "CONF", "FLAG"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._update_preview)
        self._table_card = QFrame()
        self._table_card.setObjectName("monitorPanel")
        table_card_layout = QVBoxLayout(self._table_card)
        table_card_layout.setContentsMargins(12, 12, 12, 12)
        table_card_layout.setSpacing(10)
        table_card_layout.addWidget(self._table)

        self._side_card = QFrame()
        self._side_card.setObjectName("monitorPanel")
        side = QVBoxLayout(self._side_card)
        side.setContentsMargins(12, 12, 12, 12)
        side.setSpacing(10)
        self._preview = QLabel("No plate selected")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(280, 220)
        self._preview.setObjectName("dropZone")
        side.addWidget(self._preview)

        self._details = QLabel("")
        self._details.setWordWrap(True)
        self._details.setObjectName("pageSubtitle")
        side.addWidget(self._details)

        self._sequence_table = QTableWidget(0, 4)
        self._sequence_table.setHorizontalHeaderLabels(["TIME", "SOURCE", "CONF", "STATE"])
        self._sequence_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._sequence_table.verticalHeader().setVisible(False)
        self._sequence_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._sequence_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._sequence_table.setAlternatingRowColors(True)
        self._sequence_table.itemSelectionChanged.connect(self._update_sequence_preview)
        side.addWidget(self._sequence_table)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Operator notes for this plate...")
        self._notes.setFixedHeight(90)
        side.addWidget(self._notes)

        self._flag_btn = QPushButton("FLAG / UNFLAG PLATE")
        self._flag_btn.setObjectName("secondaryButton")
        self._flag_btn.clicked.connect(self._toggle_flag)
        side.addWidget(self._flag_btn)

        for text, handler in (
            ("DELETE SNAPSHOT", self._delete_selected_snapshot),
            ("DELETE HISTORY", self._delete_selected_history),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            side.addWidget(btn)
        side.addStretch()
        self._content_grid.addWidget(self._table_card, 0, 0)
        self._content_grid.addWidget(self._side_card, 0, 1)
        self._content_grid.setColumnStretch(0, 3)
        self._content_grid.setColumnStretch(1, 1)

        layout.addLayout(self._content_grid, 1)
        self.apply_responsive_layout("medium", 1366)

    def refresh(self):
        from_date, to_date = self._resolve_time_window()
        matches = search_plate_log(
            self._plate_edit.text(),
            source_filter=self._source_edit.text(),
            watchlist_only=self._watchlist_only.isChecked(),
            from_date=from_date,
            to_date=to_date,
        )
        matches = [
            match
            for match in matches
            if self._confidence_match(match.get("confidence"))
        ]
        self._all_matches = matches
        groups = grouped_plate_history(matches)
        self._grouped_matches = groups
        self._table.setRowCount(len(groups))
        for row_index, group in enumerate(groups):
            values = [
                group["plate"],
                str(group["count"]),
                str(group["first_seen"]).split(" ")[-1],
                str(group["last_seen"]).split(" ")[-1],
                "--" if group["avg_confidence"] is None else f"{float(group['avg_confidence']):.2f}",
                "FLAGGED" if group["flagged"] else "OPEN",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, group)
                self._table.setItem(row_index, column, item)
                if group["watchlist_hit"]:
                    item.setBackground(Qt.GlobalColor.darkRed)
                elif group["flagged"]:
                    item.setBackground(Qt.GlobalColor.darkYellow)
                elif group["avg_confidence"] is not None and float(group["avg_confidence"]) < 0.75:
                    item.setBackground(Qt.GlobalColor.darkYellow)
        if groups:
            self._table.selectRow(0)
        else:
            self._preview.setText("No plate selected")
            self._preview.setPixmap(QPixmap())
            self._details.setText("No matching detections.")
            self._sequence_table.setRowCount(0)
            self._update_summary(None)

    def _selected_match(self) -> dict[str, object] | None:
        items = self._table.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _update_preview(self):
        match = self._selected_match()
        if not match:
            return
        related = list(match["matches"])
        confidences = [entry["confidence"] for entry in related if entry["confidence"] is not None]
        avg_conf = f"{(sum(confidences) / len(confidences)):.2f}" if confidences else "--"
        latest = related[-1] if related else None
        snapshot_path = Path(str(latest.get("snapshot_path") or "")) if latest else Path()
        self._details.setText(
            f"Plate: {match['plate']}\n"
            f"Sightings: {len(related)}\n"
            f"First seen: {match['first_seen']}\n"
            f"Last seen: {match['last_seen']}\n"
            f"Average confidence: {avg_conf}\n"
            f"Sources: {', '.join(match['sources'])}\n"
            f"Watchlist hit: {'Yes' if match['watchlist_hit'] else 'No'}"
        )
        self._update_summary(match["plate"])
        self._notes.setPlainText(str(match.get("note", "")))
        self._flag_btn.setText("UNFLAG PLATE" if match["flagged"] else "FLAG PLATE")
        self._sequence_table.setRowCount(len(related))
        for row_index, entry in enumerate(reversed(related[-20:])):
            values = [
                str(entry["timestamp"]).split(" ")[-1],
                str(entry["source"]),
                "--" if entry["confidence"] is None else f"{float(entry['confidence']):.2f}",
                "WATCHLIST" if entry["watchlist_hit"] else "CLEAR",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self._sequence_table.setItem(row_index, column, item)
        if snapshot_path.exists():
            pixmap = QPixmap(str(snapshot_path))
            self._preview.setPixmap(
                pixmap.scaled(
                    self._preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._preview.setText("")
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("Snapshot unavailable")

    def _open_selected_snapshot(self):
        entry = self._selected_sequence_entry()
        if not entry:
            return
        snapshot_path = Path(str(entry.get("snapshot_path") or ""))
        if snapshot_path.exists():
            QMessageBox.information(
                self, "Snapshot", f"Snapshot saved at:\n{snapshot_path}"
            )

    def _delete_selected_snapshot(self):
        entry = self._selected_sequence_entry()
        if not entry:
            return
        snapshot_path = str(entry.get("snapshot_path") or "")
        if not snapshot_path:
            QMessageBox.warning(self, "Delete Snapshot", "No snapshot is linked to this history entry.")
            return
        reply = QMessageBox.question(
            self,
            "Delete Snapshot",
            f"Delete snapshot file?\n{snapshot_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if delete_snapshot_file(snapshot_path):
            QMessageBox.information(self, "Delete Snapshot", "Snapshot deleted.")
        else:
            QMessageBox.warning(self, "Delete Snapshot", "Snapshot file could not be deleted.")
        self.refresh()

    def _delete_selected_history(self):
        entry = self._selected_sequence_entry()
        if not entry:
            return
        reply = QMessageBox.question(
            self,
            "Delete History",
            f"Delete selected history entry for {entry['plate']} at {entry['timestamp']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        entries_to_delete = [entry]
        deleted = delete_history_entries(entries_to_delete)
        for item in entries_to_delete:
            delete_snapshot_file(item.get("snapshot_path"))
        QMessageBox.information(
            self,
            "Delete History",
            f"Deleted {deleted} history entr{'y' if deleted == 1 else 'ies'}.",
        )
        self.refresh()

    def _resolve_time_window(self) -> tuple[str, str]:
        preset = self._time_preset.currentText()
        now = datetime.now()
        if preset == "Last 1 Hour":
            start = now - timedelta(hours=1)
        elif preset == "Last 24 Hours":
            start = now - timedelta(days=1)
        elif preset == "Last 7 Days":
            start = now - timedelta(days=7)
        else:
            return "", ""
        return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")

    def _confidence_match(self, confidence: object) -> bool:
        if confidence is None:
            return True
        value = float(confidence)
        return self._conf_min.value() <= value <= self._conf_max.value()

    def _update_summary(self, plate: str | None):
        if not plate:
            for _, label in (self._seen_count, self._first_seen, self._last_seen, self._avg_conf):
                label.setText("--")
            return
        related = [entry for entry in self._all_matches if entry["plate"] == plate]
        confidences = [float(entry["confidence"]) for entry in related if entry["confidence"] is not None]
        first_seen = related[0]["timestamp"] if related else "--"
        last_seen = related[-1]["timestamp"] if related else "--"
        self._seen_count[1].setText(str(len(related)))
        self._first_seen[1].setText(first_seen.split(" ")[-1] if first_seen != "--" else "--")
        self._last_seen[1].setText(last_seen.split(" ")[-1] if last_seen != "--" else "--")
        self._avg_conf[1].setText(f"{(sum(confidences) / len(confidences)) * 100:.0f}%" if confidences else "--")

    def _selected_sequence_entry(self) -> dict[str, object] | None:
        items = self._sequence_table.selectedItems()
        if not items:
            match = self._selected_match()
            if match and match["matches"]:
                return match["matches"][-1]
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _update_sequence_preview(self):
        entry = self._selected_sequence_entry()
        if not entry:
            return
        snapshot_path = Path(str(entry.get("snapshot_path") or ""))
        if snapshot_path.exists():
            pixmap = QPixmap(str(snapshot_path))
            self._preview.setPixmap(
                pixmap.scaled(
                    self._preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._preview.setText("")

    def _toggle_flag(self):
        match = self._selected_match()
        if not match:
            return
        flagged = not bool(match["flagged"])
        save_case_flag(str(match["plate"]), flagged, self._notes.toPlainText())
        self.refresh()

    def _show_sequence_summary(self):
        match = self._selected_match()
        if not match:
            return
        related = [entry for entry in self._all_matches if entry["plate"] == match["plate"]]
        if not related:
            return
        QMessageBox.information(
            self,
            "Case Bundle",
            "\n".join(
                f"{entry['timestamp']} | {entry['source']} | "
                f"{entry['confidence'] if entry['confidence'] is not None else '--'}"
                for entry in related[:20]
            ),
        )

    def _add_selected_to_watchlist(self):
        match = self._selected_match()
        if not match:
            return
        entries = watchlist_entries()
        if match["plate"] not in entries:
            entries.append(str(match["plate"]))
            save_watchlist_entries(entries)
        QMessageBox.information(self, "Watchlist", f"{match['plate']} added to watchlist")

    def apply_responsive_layout(self, breakpoint: str, window_width: int):
        margins = {
            "small": (16, 16, 16, 12),
            "medium": (22, 22, 22, 16),
            "large": (28, 28, 28, 24),
        }[breakpoint]
        self._root_layout.setContentsMargins(*margins)

        while self._filters_grid.count():
            self._filters_grid.takeAt(0)

        filter_widgets = [
            self._plate_edit,
            self._source_edit,
            self._time_preset,
            self._search_btn,
        ]
        columns = 2 if breakpoint == "small" else (3 if breakpoint == "medium" else 4)
        for index, widget in enumerate(filter_widgets):
            row = index // columns
            column = index % columns
            self._filters_grid.addWidget(widget, row, column)

        while self._content_grid.count():
            self._content_grid.takeAt(0)

        if breakpoint == "small":
            self._content_grid.addWidget(self._table_card, 0, 0)
            self._content_grid.addWidget(self._side_card, 1, 0)
            self._preview.setMinimumHeight(200)
        else:
            self._content_grid.addWidget(self._table_card, 0, 0)
            self._content_grid.addWidget(self._side_card, 0, 1)
            self._preview.setMinimumHeight(220 if breakpoint == "medium" else 260)


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)
    camera_config_changed = pyqtSignal(dict)
    theme_changed = pyqtSignal(str)  # Emits 'dark' or 'light'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._confidence = None
        self._frame_skip = None
        self._save_snapshots = None
        self._watchlist_alerts = None
        self._sound_alerts = None
        self._camera_indices = None
        self._ip_camera_urls = None
        self._default_camera = None
        self._auto_start_cameras = None
        self._scan_cameras_btn = None
        self._test_camera_btn = None
        self._camera_status_label = None
        self._camera_preview = None
        self._camera_validation = None
        self._model_selector = None
        self._theme_combo = None
        self._path_edits = {}
        self._field_labels: list[QLabel] = []
        self._main_layout = None
        self._build_ui()
        self._load()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(28, 28, 28, 24)
        main_layout.setSpacing(0)
        self._main_layout = main_layout

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        subtitle = QLabel("System control for cameras, detection runtime, storage, and alerts")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        main_layout.addLayout(header)
        main_layout.addSpacing(18)

        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")
        self._tabs = tabs

        general_tab = self._tab_page()
        general_tab.layout().addWidget(
            self._create_card("Appearance", [("Theme", self._create_theme_selector())])
        )
        general_tab.layout().addWidget(
            self._create_card(
                "General",
                [("Auto-start", self._create_checkbox(
                    "Auto-load saved cameras and start detection on launch",
                    "auto_start_cameras",
                ))],
            )
        )
        general_tab.layout().addStretch()
        tabs.addTab(general_tab, "General")

        cameras_tab = self._tab_page()
        cameras_tab.layout().addWidget(
            self._create_card(
                "Camera Command",
                [
                    ("Scan Cameras", self._create_scan_section()),
                    ("Camera Indices", self._create_line_edit("e.g., 0,1,2", "camera_indices")),
                    ("IP / RTSP URLs", self._create_text_edit(
                        "One source per line, e.g.\nrtsp://user:pass@192.168.1.10/stream",
                        "ip_camera_urls",
                    )),
                    ("Default Camera", self._create_spin_box(-1, 10, "default_camera", "None")),
                    ("Validation", self._create_validation_label()),
                    ("Live Preview", self._create_camera_preview()),
                ],
            )
        )
        cameras_tab.layout().addStretch()
        tabs.addTab(cameras_tab, "Cameras")

        detection_tab = self._tab_page()
        detection_tab.layout().addWidget(
            self._create_card(
                "Detection",
                [
                    ("Confidence Threshold", self._create_confidence_slider()),
                    ("Frame Skip", self._create_frame_skip_slider()),
                    ("Model Selector", self._create_model_selector()),
                ],
            )
        )
        detection_tab.layout().addStretch()
        tabs.addTab(detection_tab, "Detection")

        storage_tab = self._tab_page()
        storage_tab.layout().addWidget(
            self._create_card(
                "Storage",
                [
                    ("Save Snapshots", self._create_checkbox(
                        "Save confirmed snapshots automatically",
                        "save_snapshots",
                    )),
                    ("Settings", self._create_editable_path_display("Settings", get_settings_path())),
                    ("Watchlist", self._create_editable_path_display("Watchlist", get_watchlist_runtime_path())),
                    ("Plate Log", self._create_editable_path_display("Plate Log", get_plate_log_runtime_path())),
                    ("Snapshots", self._create_editable_path_display("Snapshots", get_snapshot_dir())),
                    ("Videos", self._create_editable_path_display("Videos", get_output_video_dir())),
                ],
            )
        )
        storage_tab.layout().addStretch()
        tabs.addTab(storage_tab, "Storage")

        alerts_tab = self._tab_page()
        alerts_tab.layout().addWidget(
            self._create_card(
                "Alerts",
                [
                    ("Watchlist Alerts", self._create_checkbox(
                        "Enable alerts for watchlist hits",
                        "watchlist_alerts",
                    )),
                    ("Sound Alert", self._create_checkbox(
                        "Play sound when a watchlist plate is detected",
                        "sound_alerts",
                    )),
                ],
            )
        )
        alerts_tab.layout().addStretch()
        tabs.addTab(alerts_tab, "Alerts")

        main_layout.addWidget(tabs)

        button_row = QHBoxLayout()
        button_row.addStretch()

        save_btn = QPushButton("SAVE SETTINGS")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        button_row.addWidget(save_btn)

        main_layout.addLayout(button_row)
        self.apply_responsive_layout("medium", 1366)

    def _create_card(self, title: str, fields: list) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")

        layout = QVBoxLayout(card)
        layout.setSpacing(16)

        title_label = QLabel(title)
        title_label.setObjectName("sectionLabel")
        layout.addWidget(title_label)

        for label, widget in fields:
            row = QHBoxLayout()
            row.setSpacing(16)

            lbl = QLabel(label)
            lbl.setObjectName("settingsFieldLabel")
            lbl.setMinimumWidth(140)
            self._field_labels.append(lbl)

            row.addWidget(lbl)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        return card

    def _create_line_edit(self, placeholder: str, attr_name: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        if attr_name == "camera_indices":
            edit.textChanged.connect(self._validate_camera_sources)
        setattr(self, f"_{attr_name}", edit)
        return edit

    def _create_spin_box(
        self, min_val: int, max_val: int, attr_name: str, special: str = None
    ) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        if special:
            spin.setSpecialValueText(special)
        setattr(self, f"_{attr_name}", spin)
        return spin

    def _create_double_spin(
        self, min_val: float, max_val: float, step: float, attr_name: str
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setDecimals(2)
        spin.setSingleStep(step)
        setattr(self, f"_{attr_name}", spin)
        return spin

    def _create_checkbox(self, text: str, attr_name: str) -> QCheckBox:
        chk = QCheckBox(text)
        setattr(self, f"_{attr_name}", chk)
        return chk

    def _create_text_edit(self, placeholder: str, attr_name: str) -> QTextEdit:
        edit = QTextEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFixedHeight(88)
        if attr_name == "ip_camera_urls":
            edit.textChanged.connect(self._validate_camera_sources)
        setattr(self, f"_{attr_name}", edit)
        return edit

    def _create_confidence_slider(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(5, 100)
        slider.setSingleStep(5)
        value = QLabel("0.50")
        value.setObjectName("pageSubtitle")
        slider.valueChanged.connect(lambda current: value.setText(f"{current / 100:.2f}"))
        layout.addWidget(slider, 1)
        layout.addWidget(value)

        self._confidence = slider
        self._confidence_label = value
        return widget

    def _create_frame_skip_slider(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(1, 10)
        value = QLabel("5")
        value.setObjectName("pageSubtitle")
        slider.valueChanged.connect(lambda current: value.setText(str(current)))
        layout.addWidget(slider, 1)
        layout.addWidget(value)

        self._frame_skip = slider
        self._frame_skip_label = value
        return widget

    def _tab_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)
        return page

    def _create_theme_selector(self) -> QWidget:
        """Create a theme selector combo box."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        layout.addWidget(self._theme_combo)
        layout.addStretch()

        return widget

    def _create_model_selector(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self._model_selector = QComboBox()
        self._model_selector.addItems(available_model_names())
        layout.addWidget(self._model_selector)
        layout.addStretch()
        return widget

    def _create_scan_section(self) -> QWidget:
        widget = QWidget()
        container = QHBoxLayout(widget)
        container.setSpacing(16)

        self._scan_cameras_btn = QPushButton("SCAN CAMERAS")
        self._scan_cameras_btn.setObjectName("secondaryButton")
        self._scan_cameras_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_cameras_btn.clicked.connect(self.scan_cameras)
        container.addWidget(self._scan_cameras_btn)

        self._test_camera_btn = QPushButton("TEST CONNECTION")
        self._test_camera_btn.setObjectName("secondaryButton")
        self._test_camera_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_camera_btn.clicked.connect(self._test_camera_connection)
        container.addWidget(self._test_camera_btn)

        self._camera_status_label = QLabel(
            "Saved sources load automatically. Scan only to discover local cameras."
        )
        self._camera_status_label.setObjectName("pageSubtitle")
        container.addWidget(self._camera_status_label)
        container.addStretch()

        return widget

    def _create_validation_label(self) -> QLabel:
        self._camera_validation = QLabel("Waiting for camera input.")
        self._camera_validation.setObjectName("validationLabel")
        self._camera_validation.setWordWrap(True)
        return self._camera_validation

    def _create_camera_preview(self) -> QLabel:
        self._camera_preview = QLabel("No preview yet")
        self._camera_preview.setObjectName("dropZone")
        self._camera_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._camera_preview.setMinimumHeight(220)
        return self._camera_preview

    def _create_editable_path_display(self, path_name: str, path: Path) -> QWidget:
        """Create an editable path display with a browse button."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        edit = QLineEdit(str(path))
        edit.setObjectName("pathDisplay")
        self._path_edits[path_name] = edit
        layout.addWidget(edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondaryButton")
        browse_btn.setMaximumWidth(100)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(
            lambda: self._browse_for_path(path_name, edit)
        )
        layout.addWidget(browse_btn)

        return widget

    def _browse_for_path(self, path_name: str, edit: QLineEdit):
        """Open file dialog to browse for a path."""
        current_path = edit.text()
        if path_name in {"Snapshots", "Videos"}:
            selected_path = QFileDialog.getExistingDirectory(
                self,
                f"Select {path_name} Directory",
                current_path if current_path else str(Path.home()),
                QFileDialog.Option.ShowDirsOnly,
            )
        else:
            selected_path, _ = QFileDialog.getSaveFileName(
                self,
                f"Select {path_name} File",
                current_path if current_path else str(Path.home()),
                "All Files (*)",
            )
        if selected_path:
            edit.setText(selected_path)

    def _validate_camera_sources(self):
        raw = self._ip_camera_urls.toPlainText().strip()
        indices = self._camera_indices.text().strip()
        if not raw:
            self._camera_status_label.setText(
                "Saved sources load automatically. Scan only to discover local cameras."
            )
        invalid_index = any(
            not part.strip().isdigit()
            for part in indices.replace("\n", ",").split(",")
            if part.strip()
        )
        invalid_urls = [
            line.strip()
            for line in raw.splitlines()
            if line.strip()
            and not line.strip().lower().startswith(("rtsp://", "http://", "https://"))
        ]
        if invalid_index:
            self._camera_validation.setText("Camera indices must contain only numbers separated by commas.")
            self._camera_indices.setProperty("invalid", True)
        elif invalid_urls:
            self._camera_status_label.setText(
                f"Invalid stream URL: {invalid_urls[0]}"
            )
            self._camera_validation.setText(f"Invalid stream URL: {invalid_urls[0]}")
            self._ip_camera_urls.setProperty("invalid", True)
        else:
            self._camera_status_label.setText("Camera sources look valid.")
            self._camera_validation.setText(
                "Connection inputs look valid. Use TEST CONNECTION for live verification."
            )
            self._ip_camera_urls.setProperty("invalid", False)
            self._camera_indices.setProperty("invalid", False)
        if not invalid_index:
            self._camera_indices.setProperty("invalid", False)
        if not invalid_urls:
            self._ip_camera_urls.setProperty("invalid", False)
        self._ip_camera_urls.style().unpolish(self._ip_camera_urls)
        self._ip_camera_urls.style().polish(self._ip_camera_urls)
        self._camera_indices.style().unpolish(self._camera_indices)
        self._camera_indices.style().polish(self._camera_indices)

    def _load(self):
        settings = load_ui_settings()
        storage_paths = load_storage_paths()
        
        # Load theme preference
        theme = settings.get("theme", "dark").lower()
        if theme == "light":
            self._theme_combo.setCurrentIndex(1)
        else:
            self._theme_combo.setCurrentIndex(0)
        
        # Load other settings
        self._confidence.setValue(int(float(settings.get("confidence_threshold", 0.5)) * 100))
        self._frame_skip.setValue(int(settings.get("frame_skip", 5)))
        self._save_snapshots.setChecked(bool(settings.get("save_snapshots", True)))
        self._watchlist_alerts.setChecked(
            bool(settings.get("watchlist_alerts_enabled", True))
        )
        self._sound_alerts.setChecked(bool(settings.get("sound_alerts_enabled", True)))

        indices = settings.get("camera_indices", "")
        self._camera_indices.setText(indices)
        self._ip_camera_urls.setPlainText(str(settings.get("ip_camera_urls", "")))
        self._default_camera.setValue(int(settings.get("default_camera", -1)))
        self._auto_start_cameras.setChecked(
            bool(settings.get("auto_start_cameras", False))
        )
        model_name = str(settings.get("model_name", "LicensePlateDetector.pt"))
        current_index = self._model_selector.findText(model_name)
        if current_index >= 0:
            self._model_selector.setCurrentIndex(current_index)
        self._path_edits["Settings"].setText(str(get_settings_path()))
        self._path_edits["Watchlist"].setText(storage_paths["watchlist_path"])
        self._path_edits["Plate Log"].setText(str(get_plate_log_runtime_path()))
        self._path_edits["Snapshots"].setText(storage_paths["snapshots_dir"])
        self._path_edits["Videos"].setText(storage_paths["videos_dir"])
        self._validate_camera_sources()

    def _save(self):
        theme_text = self._theme_combo.currentText().lower()
        self._validate_camera_sources()
        new_storage_paths = {
            "logs_dir": str(Path(self._path_edits["Plate Log"].text().strip()).parent),
            "settings_path": self._path_edits["Settings"].text().strip(),
            "plate_log_path": self._path_edits["Plate Log"].text().strip(),
            "watchlist_path": self._path_edits["Watchlist"].text().strip(),
            "snapshots_dir": self._path_edits["Snapshots"].text().strip(),
            "videos_dir": self._path_edits["Videos"].text().strip(),
        }
        settings_parent = Path(self._path_edits["Settings"].text().strip()).parent
        if settings_parent:
            new_storage_paths["logs_dir"] = str(settings_parent)
        save_storage_paths(new_storage_paths)
        
        settings = save_ui_settings(
            {
                "confidence_threshold": float(self._confidence.value() / 100.0),
                "frame_skip": int(self._frame_skip.value()),
                "save_snapshots": bool(self._save_snapshots.isChecked()),
                "watchlist_alerts_enabled": bool(self._watchlist_alerts.isChecked()),
                "sound_alerts_enabled": bool(self._sound_alerts.isChecked()),
                "camera_indices": self._camera_indices.text().strip(),
                "ip_camera_urls": self._ip_camera_urls.toPlainText().strip(),
                "default_camera": int(self._default_camera.value()),
                "auto_start_cameras": bool(self._auto_start_cameras.isChecked()),
                "model_name": self._model_selector.currentText(),
                "theme": theme_text,
            }
        )
        
        self.settings_changed.emit(settings)
        self.camera_config_changed.emit(settings)
        self.theme_changed.emit(theme_text)
        self._load()

    def scan_cameras(self):
        import sys
        import cv2

        def _get_capture(index: int):
            if sys.platform == "win32":
                return cv2.VideoCapture(index, cv2.CAP_ANY)
            return cv2.VideoCapture(index)

        found = []
        for i in range(10):
            cap = _get_capture(i)
            if cap.isOpened():
                found.append(i)
                cap.release()
        if found:
            self._camera_status_label.setText(f"Found: {found}")
            self._camera_indices.setText(",".join(map(str, found)))
            self._camera_validation.setText("Local camera scan completed successfully.")
        else:
            self._camera_status_label.setText("No cameras found")
            self._camera_validation.setText("No local cameras responded during scan.")

    def _test_camera_connection(self):
        source: int | str | None = None
        raw_indices = [part.strip() for part in self._camera_indices.text().replace("\n", ",").split(",") if part.strip()]
        if raw_indices and raw_indices[0].isdigit():
            source = int(raw_indices[0])
        else:
            urls = [line.strip() for line in self._ip_camera_urls.toPlainText().splitlines() if line.strip()]
            if urls:
                source = urls[0]
        if source is None:
            self._camera_validation.setText("Enter a camera index or stream URL before testing.")
            return
        cap = cv2.VideoCapture(source)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            self._camera_status_label.setText("Connection test failed.")
            self._camera_validation.setText("Unable to read a frame from the selected source.")
            self._camera_preview.setPixmap(QPixmap())
            self._camera_preview.setText("Preview unavailable")
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        from PyQt6.QtGui import QImage

        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self._camera_preview.setPixmap(
            QPixmap.fromImage(image).scaled(
                self._camera_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._camera_preview.setText("")
        self._camera_status_label.setText("Connection test passed.")
        self._camera_validation.setText("Live preview captured successfully.")

    def apply_responsive_layout(self, breakpoint: str, window_width: int):
        margins = {
            "small": (16, 16, 16, 12),
            "medium": (22, 22, 22, 16),
            "large": (28, 28, 28, 24),
        }[breakpoint]
        self._main_layout.setContentsMargins(*margins)

        label_width = {"small": 104, "medium": 124, "large": 140}[breakpoint]
        for label in self._field_labels:
            label.setMinimumWidth(label_width)

        self._camera_preview.setMinimumHeight(
            180 if breakpoint == "small" else 220
        )
        self._ip_camera_urls.setFixedHeight(72 if breakpoint == "small" else 88)
        self._tabs.setUsesScrollButtons(breakpoint == "small")



class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(20)
        self._root_layout = layout
        layout.addLayout(
            _page_header(
                "System Info",
                "Runtime telemetry has been moved into the Dashboard so operators stay in one workspace",
            )
        )

        notice = QFrame()
        notice.setObjectName("monitorPanel")
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(20, 20, 20, 20)
        notice_layout.setSpacing(10)
        title = QLabel("SYSTEM INFO MOVED")
        title.setObjectName("panelTitle")
        body = QLabel(
            "Open Dashboard to view device state, model runtime, storage paths, and condensed diagnostics without leaving surveillance mode."
        )
        body.setObjectName("pageSubtitle")
        body.setWordWrap(True)
        notice_layout.addWidget(title)
        notice_layout.addWidget(body)
        layout.addWidget(notice)

        self._info_labels = {}
        info_box = QGroupBox("Reference Diagnostics")
        info_layout = QGridLayout(info_box)
        info_layout.setSpacing(12)
        info_items = [
            ("device_label", "Processing Device"),
            ("model_path_label", "Model Path"),
            ("model_exists_label", "Model Status"),
            ("plate_log_label", "Plate Log"),
            ("watchlist_label", "Watchlist"),
            ("outputs_label", "Outputs Directory"),
        ]

        for idx, (key, label) in enumerate(info_items):
            key_label = QLabel(label)
            key_label.setObjectName("sectionLabel")
            val_label = QLabel("-")
            val_label.setObjectName("pageSubtitle")
            val_label.setWordWrap(True)
            self._info_labels[key] = val_label
            info_layout.addWidget(key_label, idx, 0)
            info_layout.addWidget(val_label, idx, 1)

        layout.addWidget(info_box)

        layout.addStretch()

    def refresh(self):
        status = dependency_status()

        label_map = {
            "device": "device_label",
            "model_path": "model_path_label",
            "model_exists": "model_exists_label",
            "torch": "torch_label",
            "opencv": "opencv_label",
            "awiros_anpr": "awiros_anpr_label",
            "paddle": "paddle_label",
            "safetensors": "safetensors_label",
            "ultralytics": "ultralytics_label",
            "plate_log": "plate_log_label",
            "watchlist": "watchlist_label",
            "outputs": "outputs_label",
        }

        for key, label_key in label_map.items():
            if label_key in self._info_labels:
                value = status.get(key, "N/A")
                if key == "model_exists":
                    value = "Found" if value == "Yes" else "Not Found"
                self._info_labels[label_key].setText(str(value))

    def apply_responsive_layout(self, breakpoint: str, window_width: int):
        margins = {
            "small": (16, 16, 16, 12),
            "medium": (24, 24, 24, 18),
            "large": (36, 36, 36, 24),
        }[breakpoint]
        self._root_layout.setContentsMargins(*margins)


class UserManagementPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self._refresh_users()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(20)
        self._root_layout = layout
        layout.addLayout(
            _page_header("User Management", "Manage system users and roles")
        )

        self._user_table = QTableWidget()
        self._user_table.setColumnCount(6)
        self._user_table.setHorizontalHeaderLabels(
            ["ID", "Username", "Full Name", "Role", "Created At", "Last Login"]
        )
        self._user_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._user_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._user_table)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self._new_username = QLineEdit()
        self._new_username.setPlaceholderText("Username")
        self._new_full_name = QLineEdit()
        self._new_full_name.setPlaceholderText("Full Name")
        self._new_password = QLineEdit()
        self._new_password.setPlaceholderText("Password")
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_role = QComboBox()
        self._new_role.addItems(AVAILABLE_USER_ROLES)
        self._new_role.setCurrentText("gate keeper")

        form_layout.addRow("Username:", self._new_username)
        form_layout.addRow("Full Name:", self._new_full_name)
        form_layout.addRow("Password:", self._new_password)
        form_layout.addRow("Role:", self._new_role)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("Add User")
        self._add_btn.clicked.connect(self._on_add_user)
        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.clicked.connect(self._on_delete_user)
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_users)

        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._delete_btn)
        btn_layout.addWidget(self._refresh_btn)
        btn_layout.addStretch()

        layout.addLayout(form_layout)
        layout.addLayout(btn_layout)
        self.apply_responsive_layout("medium", 1366)

    def _refresh_users(self):
        from app.storage.database import get_all_users

        users = get_all_users()
        self._user_table.setRowCount(0)
        for user in users:
            row = self._user_table.rowCount()
            self._user_table.insertRow(row)
            self._user_table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self._user_table.setItem(row, 1, QTableWidgetItem(user.username))
            self._user_table.setItem(row, 2, QTableWidgetItem(getattr(user, "full_name", "") or user.username))
            self._user_table.setItem(row, 3, QTableWidgetItem(user.role))
            self._user_table.setItem(
                row,
                4,
                QTableWidgetItem(
                    user.created_at.strftime("%Y-%m-%d %H:%M")
                    if user.created_at
                    else ""
                ),
            )
            self._user_table.setItem(
                row,
                5,
                QTableWidgetItem(
                    user.last_login.strftime("%Y-%m-%d %H:%M")
                    if user.last_login
                    else "Never"
                ),
            )

    def _on_add_user(self):
        from app.storage.database import create_user

        username = self._new_username.text().strip()
        full_name = self._new_full_name.text().strip()
        password = self._new_password.text()
        role = self._new_role.currentText().strip().lower()

        if not username or not full_name or not password:
            QMessageBox.warning(self, "Error", "Username, full name and password are required")
            return

        if role not in AVAILABLE_USER_ROLES:
            QMessageBox.warning(self, "Error", "Select a valid role")
            return

        user = create_user(username, password, role, full_name=full_name)
        if user:
            QMessageBox.information(
                self, "Success", f"User '{username}' created successfully"
            )
            self._new_username.clear()
            self._new_full_name.clear()
            self._new_password.clear()
            self._new_role.setCurrentText("gate keeper")
            self._refresh_users()
        else:
            QMessageBox.warning(
                self, "Error", "Failed to create user. Username may already exist."
            )

    def _on_delete_user(self):
        from app.storage.database import delete_user

        current_row = self._user_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Error", "Please select a user to delete")
            return

        user_id_item = self._user_table.item(current_row, 0)
        username_item = self._user_table.item(current_row, 1)

        if not user_id_item or not username_item:
            return

        user_id = int(user_id_item.text())
        username = username_item.text()

        if username == "admin":
            QMessageBox.warning(self, "Error", "Cannot delete admin user")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete user '{username}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if delete_user(user_id):
                QMessageBox.information(self, "Success", f"User '{username}' deleted")
                self._refresh_users()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete user")

    def apply_responsive_layout(self, breakpoint: str, window_width: int):
        margins = {
            "small": (16, 16, 16, 12),
            "medium": (24, 24, 24, 18),
            "large": (36, 36, 36, 24),
        }[breakpoint]
        self._root_layout.setContentsMargins(*margins)
