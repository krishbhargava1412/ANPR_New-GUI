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
    QMessageBox,
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
            ("CLEAR LOG", self._clear_log),
            ("CLEAR OUTPUTS", self._clear_outputs),
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

    def _clear_log(self):
        clear_plate_log()
        self.refresh()

    def _clear_outputs(self):
        count = clear_outputs()
        self.refresh()


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
        layout.addLayout(
            _page_header(
                "History", "Search detections, watchlist hits, and evidence snapshots"
            )
        )

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
        for widget in (
            self._plate_edit,
            self._source_edit,
            self._from_edit,
            self._to_edit,
            self._watchlist_only,
        ):
            filters.addWidget(widget)
        search_btn = QPushButton("SEARCH")
        search_btn.setObjectName("primaryButton")
        search_btn.clicked.connect(self.refresh)
        filters.addWidget(search_btn)
        layout.addLayout(filters)

        splitter_row = QHBoxLayout()

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
        self._preview.setMinimumSize(240, 180)
        self._preview.setObjectName("dropZone")
        side.addWidget(self._preview)

        self._details = QLabel("")
        self._details.setWordWrap(True)
        self._details.setObjectName("pageSubtitle")
        side.addWidget(self._details)

        for text, handler in (
            ("OPEN SNAPSHOT", self._open_selected_snapshot),
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


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)
    camera_config_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 24)
        layout.setSpacing(20)
        layout.addLayout(
            _page_header(
                "Settings",
                "Detection, storage, camera configuration, and alert settings",
            )
        )

        camera_box = QGroupBox("Camera Configuration")
        camera_form = QFormLayout(camera_box)
        camera_form.setSpacing(12)

        self._scan_cameras_btn = QPushButton("SCAN CAMERAS")
        self._scan_cameras_btn.setObjectName("secondaryButton")
        self._scan_cameras_btn.clicked.connect(self._scan_cameras)
        camera_form.addRow("", self._scan_cameras_btn)

        self._camera_status_label = QLabel("Click scan to detect available cameras")
        self._camera_status_label.setObjectName("pageSubtitle")
        camera_form.addRow("Status", self._camera_status_label)

        self._camera_indices = QLineEdit()
        self._camera_indices.setPlaceholderText("e.g., 0,1,2")
        camera_form.addRow("Camera Indices", self._camera_indices)

        self._default_camera = QSpinBox()
        self._default_camera.setRange(-1, 10)
        self._default_camera.setSpecialValueText("None")
        camera_form.addRow("Default Camera", self._default_camera)

        self._auto_start_cameras = QCheckBox("Auto-start cameras on detection")
        camera_form.addRow("Auto-start", self._auto_start_cameras)

        layout.addWidget(camera_box)

        form_box = QGroupBox("Detection Settings")
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
        save_btn = QPushButton("SAVE SETTINGS")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()

    def _load(self):
        settings = load_ui_settings()
        self._confidence.setValue(float(settings.get("confidence_threshold", 0.5)))
        self._frame_skip.setValue(int(settings.get("frame_skip", 5)))
        self._save_snapshots.setChecked(bool(settings.get("save_snapshots", True)))
        self._watchlist_alerts.setChecked(bool(settings.get("watchlist_alerts_enabled", True)))
        
        indices = settings.get("camera_indices", "")
        self._camera_indices.setText(indices)
        self._default_camera.setValue(int(settings.get("default_camera", -1)))
        self._auto_start_cameras.setChecked(bool(settings.get("auto_start_cameras", False)))

    def _save(self):
        settings = save_ui_settings(
            {
                "confidence_threshold": float(self._confidence.value()),
                "frame_skip": int(self._frame_skip.value()),
                "save_snapshots": bool(self._save_snapshots.isChecked()),
                "watchlist_alerts_enabled": bool(self._watchlist_alerts.isChecked()),
                "camera_indices": self._camera_indices.text().strip(),
                "default_camera": int(self._default_camera.value()),
                "auto_start_cameras": bool(self._auto_start_cameras.isChecked()),
            }
        )
        self.settings_changed.emit(settings)
        self.camera_config_changed.emit(settings)

    def _scan_cameras(self):
        import cv2
        found = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
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
                "System Info", "Device status, model information, and runtime diagnostics"
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
            ("easyocr_label", "EasyOCR"),
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
            "easyocr": "easyocr_label",
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
