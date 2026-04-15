from __future__ import annotations

from datetime import datetime, timedelta
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
    QMessageBox,
    QFileDialog,
    QComboBox,
    QSlider,
    QTabWidget,
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
    recent_detections,
    save_ui_settings,
    search_plate_log,
    clear_plate_log,
    clear_outputs,
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
        self._recent_table = None
        self._preview = None
        self._preview_details = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)
        layout.addLayout(_page_header("Dashboard", "Live monitoring, camera readiness, and recent evidence"))

        ticker = QFrame()
        ticker.setObjectName("tickerBar")
        ticker_row = QHBoxLayout(ticker)
        ticker_row.setContentsMargins(16, 10, 16, 10)
        self._latest_label = QLabel("")
        self._latest_label.setObjectName("tickerLabel")
        ticker_row.addWidget(self._latest_label)
        ticker_row.addStretch()
        layout.addWidget(ticker)

        row = QGridLayout()
        row.setHorizontalSpacing(12)
        row.setVerticalSpacing(12)
        for key, label in (
            ("detections", "DETECTIONS LOGGED"),
            ("plates", "UNIQUE PLATES"),
            ("rate_per_min", "PLATES / MIN"),
            ("active_cameras", "ACTIVE CAMERAS"),
            ("avg_confidence", "AVG CONFIDENCE"),
            ("watchlist_hits", "WATCHLIST HITS"),
        ):
            card, value_label = _stat_card_widget(label)
            self._value_labels[key] = value_label
            index = len(self._value_labels) - 1
            row.addWidget(card, index // 3, index % 3)
        layout.addLayout(row)

        actions = QHBoxLayout()
        for text, handler in (
            ("REFRESH", self.refresh),
            ("CLEAR LOG", self._clear_log),
            ("CLEAR OUTPUTS", self._clear_outputs),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)

        lower = QHBoxLayout()
        lower.setSpacing(14)

        self._recent_table = QTableWidget(0, 5)
        self._recent_table.setHorizontalHeaderLabels(
            ["TIME", "PLATE", "SOURCE", "CONF", "STATUS"]
        )
        self._recent_table.horizontalHeader().setStretchLastSection(True)
        self._recent_table.verticalHeader().setVisible(False)
        self._recent_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._recent_table.itemSelectionChanged.connect(self._update_preview)
        lower.addWidget(self._recent_table, stretch=3)

        side = QVBoxLayout()
        side.setSpacing(10)
        side_card = QFrame()
        side_card.setObjectName("monitorPanel")
        side_card_layout = QVBoxLayout(side_card)
        side_card_layout.setContentsMargins(14, 14, 14, 14)
        side_card_layout.setSpacing(10)
        title = QLabel("Latest Evidence")
        title.setObjectName("panelTitle")
        side_card_layout.addWidget(title)
        self._preview = QLabel("No recent snapshot")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(280, 200)
        self._preview.setObjectName("dropZone")
        side_card_layout.addWidget(self._preview)
        self._preview_details = QLabel("Recent detections will appear here.")
        self._preview_details.setObjectName("pageSubtitle")
        self._preview_details.setWordWrap(True)
        side_card_layout.addWidget(self._preview_details)
        side.addWidget(side_card)
        lower.addLayout(side, stretch=2)
        layout.addLayout(lower, stretch=1)

    def refresh(self):
        stats = dashboard_stats()
        for key, label in self._value_labels.items():
            label.setText(stats.get(key, "0"))
        self._latest_label.setText(
            f"LIVE ACTIVITY  |  Last detection: {stats['latest']}  |  "
            f"{stats.get('active_cameras', '0')} configured cameras  |  "
            f"{stats.get('rate_per_min', '0.0')} plates/min"
        )

        matches = recent_detections(12)
        self._recent_table.setRowCount(len(matches))
        for row_index, match in enumerate(matches):
            status = "WATCHLIST" if match["watchlist_hit"] else "CLEAR"
            values = [
                match["timestamp"].split(" ")[-1],
                match["plate"],
                match["source"],
                "" if match["confidence"] is None else f"{match['confidence']:.2f}",
                status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, match)
                self._recent_table.setItem(row_index, column, item)
        if matches:
            self._recent_table.selectRow(0)
        else:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("No recent snapshot")
            self._preview_details.setText("Recent detections will appear here.")

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
        snapshot_path = Path(str(match.get("snapshot_path") or ""))
        self._preview_details.setText(
            f"Plate: {match['plate']}\n"
            f"Source: {match['source']}\n"
            f"Time: {match['timestamp']}\n"
            f"Confidence: {match['confidence'] if match['confidence'] is not None else '--'}"
        )
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


class HistoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._all_matches: list[dict[str, object]] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(16)
        layout.addLayout(
            _page_header(
                "History", "Investigation view for detections, repeat sightings, and evidence"
            )
        )

        filters = QHBoxLayout()
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
            filters.addWidget(widget)
        search_btn = QPushButton("SEARCH")
        search_btn.setObjectName("primaryButton")
        search_btn.clicked.connect(self.refresh)
        filters.addWidget(search_btn)
        layout.addLayout(filters)

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

        splitter_row = QHBoxLayout()
        splitter_row.setSpacing(14)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Timestamp", "Plate", "Source", "Confidence", "Watchlist"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._update_preview)
        splitter_row.addWidget(self._table, stretch=3)

        side = QVBoxLayout()
        self._preview = QLabel("No snapshot selected")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(280, 220)
        self._preview.setObjectName("dropZone")
        side.addWidget(self._preview)

        self._details = QLabel("")
        self._details.setWordWrap(True)
        self._details.setObjectName("pageSubtitle")
        side.addWidget(self._details)

        for text, handler in (
            ("OPEN SNAPSHOT", self._open_selected_snapshot),
            ("PLAY SEQUENCE", self._show_sequence_summary),
        ):
            btn = QPushButton(text)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(handler)
            side.addWidget(btn)
        side.addStretch()
        splitter_row.addLayout(side, stretch=2)

        layout.addLayout(splitter_row)

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
                if match["watchlist_hit"]:
                    item.setBackground(Qt.GlobalColor.darkRed)
                elif match["confidence"] is not None and float(match["confidence"]) < 0.75:
                    item.setBackground(Qt.GlobalColor.darkYellow)
        if matches:
            self._table.selectRow(0)
        else:
            self._preview.setText("No snapshot selected")
            self._preview.setPixmap(QPixmap())
            self._details.setText("No matching detections.")
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
        related = [entry for entry in self._all_matches if entry["plate"] == match["plate"]]
        confidences = [entry["confidence"] for entry in related if entry["confidence"] is not None]
        avg_conf = f"{(sum(confidences) / len(confidences)):.2f}" if confidences else "--"
        snapshot_path = Path(str(match.get("snapshot_path") or ""))
        self._details.setText(
            f"Plate: {match['plate']}\n"
            f"Source: {match['source']}\n"
            f"Time: {match['timestamp']}\n"
            f"Snapshot: {snapshot_path if snapshot_path else 'None'}\n"
            f"Sightings: {len(related)}\n"
            f"Average confidence: {avg_conf}"
        )
        self._update_summary(match["plate"])
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
        match = self._selected_match()
        if not match:
            return
        snapshot_path = Path(str(match.get("snapshot_path") or ""))
        if snapshot_path.exists():
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.information(
                self, "Snapshot", f"Snapshot saved at:\n{snapshot_path}"
            )

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

    def _show_sequence_summary(self):
        match = self._selected_match()
        if not match:
            return
        related = [entry for entry in self._all_matches if entry["plate"] == match["plate"]]
        if not related:
            return
        QMessageBox.information(
            self,
            "Sequence",
            "\n".join(
                f"{entry['timestamp']} | {entry['source']} | "
                f"{entry['confidence'] if entry['confidence'] is not None else '--'}"
                for entry in related[:20]
            ),
        )


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
        self._camera_indices = None
        self._ip_camera_urls = None
        self._default_camera = None
        self._auto_start_cameras = None
        self._scan_cameras_btn = None
        self._camera_status_label = None
        self._theme_combo = None
        self._path_edits = {}
        self._build_ui()
        self._load()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 24)
        main_layout.setSpacing(0)

        header = QVBoxLayout()
        header.setSpacing(4)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Configure detection, cameras, storage, alerts, and appearance")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        main_layout.addLayout(header)
        main_layout.addSpacing(18)

        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")

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
                "Camera Configuration",
                [
                    ("Scan Cameras", self._create_scan_section()),
                    ("Camera Indices", self._create_line_edit("e.g., 0,1,2", "camera_indices")),
                    ("IP / RTSP URLs", self._create_text_edit(
                        "One source per line, e.g.\nrtsp://user:pass@192.168.1.10/stream",
                        "ip_camera_urls",
                    )),
                    ("Default Camera", self._create_spin_box(-1, 10, "default_camera", "None")),
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
                    ("Frame Skip", self._create_spin_box(1, 10, "frame_skip")),
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
                    ("Settings", self._create_editable_path_display("Settings", SETTINGS_PATH)),
                    ("Watchlist", self._create_editable_path_display("Watchlist", WATCHLIST_PATH)),
                    ("Plate Log", self._create_editable_path_display("Plate Log", PLATE_LOG_PATH)),
                    ("Snapshots", self._create_editable_path_display("Snapshots", SNAPSHOT_DIR)),
                ],
            )
        )
        storage_tab.layout().addStretch()
        tabs.addTab(storage_tab, "Storage")

        alerts_tab = self._tab_page()
        alerts_tab.layout().addWidget(
            self._create_card(
                "Alerts",
                [("Watchlist Alerts", self._create_checkbox(
                    "Enable alerts for watchlist hits",
                    "watchlist_alerts",
                ))],
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

            row.addWidget(lbl)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        return card

    def _create_line_edit(self, placeholder: str, attr_name: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
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

    def _create_scan_section(self) -> QWidget:
        widget = QWidget()
        container = QHBoxLayout(widget)
        container.setSpacing(16)

        self._scan_cameras_btn = QPushButton("SCAN CAMERAS")
        self._scan_cameras_btn.setObjectName("secondaryButton")
        self._scan_cameras_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_cameras_btn.clicked.connect(self.scan_cameras)
        container.addWidget(self._scan_cameras_btn)

        self._camera_status_label = QLabel(
            "Saved sources load automatically. Scan only to discover local cameras."
        )
        self._camera_status_label.setObjectName("pageSubtitle")
        container.addWidget(self._camera_status_label)
        container.addStretch()

        return widget

    def _create_editable_path_display(self, path_name: str, path: Path) -> QWidget:
        """Create an editable path display with a browse button."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        edit = QLineEdit(str(path))
        edit.setReadOnly(True)
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
        selected_path = QFileDialog.getExistingDirectory(
            self,
            f"Select {path_name} Directory",
            current_path if current_path else str(Path.home()),
            QFileDialog.Option.ShowDirsOnly
        )
        if selected_path:
            edit.setText(selected_path)

    def _validate_camera_sources(self):
        raw = self._ip_camera_urls.toPlainText().strip()
        if not raw:
            self._camera_status_label.setText(
                "Saved sources load automatically. Scan only to discover local cameras."
            )
            return
        invalid = [
            line.strip()
            for line in raw.splitlines()
            if line.strip()
            and not line.strip().lower().startswith(("rtsp://", "http://", "https://"))
        ]
        if invalid:
            self._camera_status_label.setText(
                f"Invalid stream URL: {invalid[0]}"
            )
        else:
            self._camera_status_label.setText("Camera sources look valid.")

    def _load(self):
        settings = load_ui_settings()
        
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

        indices = settings.get("camera_indices", "")
        self._camera_indices.setText(indices)
        self._ip_camera_urls.setPlainText(str(settings.get("ip_camera_urls", "")))
        self._default_camera.setValue(int(settings.get("default_camera", -1)))
        self._auto_start_cameras.setChecked(
            bool(settings.get("auto_start_cameras", False))
        )

    def _save(self):
        theme_text = self._theme_combo.currentText().lower()
        
        settings = save_ui_settings(
            {
                "confidence_threshold": float(self._confidence.value() / 100.0),
                "frame_skip": int(self._frame_skip.value()),
                "save_snapshots": bool(self._save_snapshots.isChecked()),
                "watchlist_alerts_enabled": bool(self._watchlist_alerts.isChecked()),
                "camera_indices": self._camera_indices.text().strip(),
                "ip_camera_urls": self._ip_camera_urls.toPlainText().strip(),
                "default_camera": int(self._default_camera.value()),
                "auto_start_cameras": bool(self._auto_start_cameras.isChecked()),
                "theme": theme_text,
            }
        )
        
        self.settings_changed.emit(settings)
        self.camera_config_changed.emit(settings)
        self.theme_changed.emit(theme_text)

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
        else:
            self._camera_status_label.setText("No cameras found")



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
        layout.addLayout(
            _page_header(
                "System Info",
                "Device status, model information, and runtime diagnostics",
            )
        )

        info_box = QGroupBox("Runtime Information")
        info_layout = QGridLayout(info_box)
        info_layout.setSpacing(12)

        self._info_labels = {}
        info_items = [
            ("device_label", "Processing Device"),
            ("model_path_label", "Model Path"),
            ("model_exists_label", "Model Status"),
            ("torch_label", "PyTorch Version"),
            ("opencv_label", "OpenCV"),
            ("awiros_anpr_label", "Awiros ANPR OCR"),
            ("paddle_label", "PaddlePaddle"),
            ("safetensors_label", "SafeTensors"),
            ("ultralytics_label", "Ultralytics"),
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

        row = QHBoxLayout()
        refresh_btn = QPushButton("REFRESH")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        row.addWidget(refresh_btn)
        row.addStretch()
        layout.addLayout(row)
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


class UserManagementPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self._refresh_users()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(20)
        layout.addLayout(
            _page_header("User Management", "Manage system users and roles")
        )

        self._user_table = QTableWidget()
        self._user_table.setColumnCount(5)
        self._user_table.setHorizontalHeaderLabels(
            ["ID", "Username", "Role", "Created At", "Last Login"]
        )
        self._user_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._user_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._user_table)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self._new_username = QLineEdit()
        self._new_username.setPlaceholderText("Username")
        self._new_password = QLineEdit()
        self._new_password.setPlaceholderText("Password")
        self._new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_role = QLineEdit()
        self._new_role.setPlaceholderText("Role (user/admin)")
        self._new_role.setText("user")

        form_layout.addRow("Username:", self._new_username)
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

    def _refresh_users(self):
        from app.storage.database import get_all_users

        users = get_all_users()
        self._user_table.setRowCount(0)
        for user in users:
            row = self._user_table.rowCount()
            self._user_table.insertRow(row)
            self._user_table.setItem(row, 0, QTableWidgetItem(str(user.id)))
            self._user_table.setItem(row, 1, QTableWidgetItem(user.username))
            self._user_table.setItem(row, 2, QTableWidgetItem(user.role))
            self._user_table.setItem(
                row,
                3,
                QTableWidgetItem(
                    user.created_at.strftime("%Y-%m-%d %H:%M")
                    if user.created_at
                    else ""
                ),
            )
            self._user_table.setItem(
                row,
                4,
                QTableWidgetItem(
                    user.last_login.strftime("%Y-%m-%d %H:%M")
                    if user.last_login
                    else "Never"
                ),
            )

    def _on_add_user(self):
        from app.storage.database import create_user

        username = self._new_username.text().strip()
        password = self._new_password.text()
        role = self._new_role.text().strip().lower()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Username and password are required")
            return

        if role not in ("user", "admin"):
            QMessageBox.warning(self, "Error", "Role must be 'user' or 'admin'")
            return

        user = create_user(username, password, role)
        if user:
            QMessageBox.information(
                self, "Success", f"User '{username}' created successfully"
            )
            self._new_username.clear()
            self._new_password.clear()
            self._new_role.setText("user")
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
