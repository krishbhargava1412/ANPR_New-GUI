from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QMenu,
    QMessageBox,
    QLineEdit,
)

from app.camera.camera_worker import CameraWorker
from app.detection.detection_page import DetectionPage
from app.services.app_runtime import get_saved_camera_sources, load_ui_settings
from app.ui.sidebar import Sidebar
from app.ui.workspace_pages import AboutPage, DashboardPage, HistoryPage, SettingsPage
from app.ui.login import show_login_dialog, show_logout_dialog, get_current_user
from app.storage.session import is_authenticated, is_admin


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(12)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        subtitle_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision - ANPR Command Center")
        self.setMinimumSize(QSize(1100, 700))
        self._user_menu = None
        self._create_menu_bar()
        self._build_ui()
        self._initialize_runtime()
        self._camera_workers: dict[int, CameraWorker] = {}
        self._apply_saved_camera_config(load_ui_settings())
        self._check_authentication()

    def _initialize_runtime(self):
        from app.detection.legacy_backend import get_plate_model, _get_safe_device
        from app.services.app_runtime import dependency_status

        device = _get_safe_device()
        print(f"[INFO] Using processing device: {device}")

        status = dependency_status()
        print(f"[INFO] Device detected: {status['device']}")

        try:
            get_plate_model()
            print(f"[INFO] Model loaded successfully on {device}")
        except Exception as e:
            print(f"[WARN] Model loading failed: {e}")

        self.statusBar().showMessage(f"Device: {device} | Ready")

    def _check_authentication(self):
        if not is_authenticated():
            self._show_login_dialog()

    def _show_login_dialog(self):
        if show_login_dialog(self):
            self._update_user_menu()
            self.statusBar().showMessage("Login successful")
        else:
            QMessageBox.warning(
                self,
                "Authentication Required",
                "You must login to use the application.",
            )

    def _create_menu_bar(self):
        menubar = self.menuBar()

        self._user_menu = menubar.addMenu("User")
        self._update_user_menu()

    def _update_user_menu(self):
        if self._user_menu is None:
            return
        self._user_menu.clear()

        user = get_current_user()
        if user:
            action = self._user_menu.addAction(
                f"Logged in: {user['username']} ({user['role']})"
            )
            action.setEnabled(False)

            self._user_menu.addSeparator()

            change_pw = self._user_menu.addAction("Change Password")
            change_pw.triggered.connect(self._on_change_password)

            self._user_menu.addSeparator()

            logout_action = self._user_menu.addAction("Logout")
            logout_action.triggered.connect(self._on_logout)

            if is_admin():
                self._user_menu.addSeparator()
                manage_users = self._user_menu.addAction("Manage Users")
                manage_users.triggered.connect(self._show_user_management)
        else:
            login_action = self._user_menu.addAction("Login")
            login_action.triggered.connect(self._on_login)

    def _on_change_password(self):
        from app.ui.login import show_change_password_dialog

        show_change_password_dialog(self)

    def _on_login(self):
        if show_login_dialog(self):
            self._update_user_menu()
            self.statusBar().showMessage("Login successful")
        else:
            QMessageBox.warning(self, "Login Required", "You must login to continue.")

    def _on_logout(self):
        if show_logout_dialog(self):
            self._update_user_menu()
            self.statusBar().showMessage("Logged out")
            self._check_authentication()

    def _show_user_management(self):
        if not is_admin():
            QMessageBox.warning(
                self, "Access Denied", "Only administrators can manage users."
            )
            return
        from app.ui.workspace_pages import UserManagementPage

        self._user_management_page = UserManagementPage()
        self._stack.addWidget(self._user_management_page)
        self._stack.setCurrentWidget(self._user_management_page)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.page_changed.connect(self._switch_page)
        root.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("contentArea")
        root.addWidget(self._stack)

        self._dashboard_page = DashboardPage()
        self._detection_page = DetectionPage()
        self._history_page = HistoryPage()
        self._settings_page = SettingsPage()
        self._about_page = AboutPage()

        pages = [
            ("dashboard", self._dashboard_page),
            ("detection", self._detection_page),
            ("history", self._history_page),
            ("settings", self._settings_page),
            ("about", self._about_page),
        ]

        self._page_widgets: dict[str, QWidget] = {}
        for page_id, widget in pages:
            self._stack.addWidget(widget)
            self._page_widgets[page_id] = widget

        self._settings_page.settings_changed.connect(self._on_settings_changed)
        self._settings_page.camera_config_changed.connect(
            self._on_camera_config_changed
        )

        self._switch_page("dashboard")
        self.statusBar().showMessage("Ready")

    def _on_camera_config_changed(self, settings: dict):
        self._apply_saved_camera_config(settings)

    def _on_settings_changed(self, settings: dict):
        self._detection_page.apply_runtime_settings(settings)
        self._about_page.refresh()

    def _apply_saved_camera_config(self, settings: dict):
        desired_sources = get_saved_camera_sources(settings)
        desired_ids = {int(entry["camera_id"]) for entry in desired_sources}

        for camera_id in list(self._camera_workers):
            if camera_id in desired_ids:
                continue
            self._camera_workers[camera_id].stop()
            self._camera_workers.pop(camera_id, None)
            self._detection_page.unregister_camera(camera_id)

        for entry in desired_sources:
            camera_id = int(entry["camera_id"])
            if camera_id not in self._camera_workers:
                worker = CameraWorker(
                    camera_index=camera_id,
                    fps=30,
                    source=entry["source"],
                    display_name=str(entry["label"]),
                )
                worker.frame_ready.connect(self._detection_page.on_frame_ready)
                self._camera_workers[camera_id] = worker
                worker.start()
            self._detection_page.register_camera(camera_id, str(entry["label"]))

        if bool(settings.get("auto_start_cameras", False)) and desired_sources:
            self._detection_page.start_detection()

    def _switch_page(self, page_id: str):
        if not is_authenticated():
            self._show_login_dialog()
            return

        widget = self._page_widgets.get(page_id)
        if not widget:
            return
        self._stack.setCurrentWidget(widget)
        if page_id == "dashboard":
            self._dashboard_page.refresh()
        elif page_id == "history":
            self._history_page.refresh()
        elif page_id == "about":
            self._about_page.refresh()
        self.statusBar().showMessage(page_id.upper())

    def closeEvent(self, event):
        for worker in self._camera_workers.values():
            worker.stop()
        super().closeEvent(event)
