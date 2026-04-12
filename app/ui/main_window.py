from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget, QPushButton, QMenu

from app.camera.camera_page import CameraPage
from app.detection.detection_page import DetectionPage
from app.ui.sidebar import Sidebar
from app.ui.workspace_pages import AboutPage, DashboardPage, HistoryPage, PipelinePage, SettingsPage
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
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision - ANPR Command Center")
        self.setMinimumSize(QSize(1100, 700))
        self._build_ui()
        self._create_menu_bar()

    def _create_menu_bar(self):
        menubar = self.menuBar()

        self._user_menu = menubar.addMenu("User")
        self._update_user_menu()

    def _update_user_menu(self):
        self._user_menu.clear()

        user = get_current_user()
        if user:
            user_info = QLabel(f"Logged in: {user.username} ({user.role})")
            user_info.setStyleSheet("padding: 4px;")
            action = self._user_menu.addAction(f"Logged in: {user.username} ({user.role})")
            action.setEnabled(False)

            if is_admin():
                admin_action = self._user_menu.addAction("Admin Mode")
                admin_action.setEnabled(False)

            self._user_menu.addSeparator()

            logout_action = QPushButton("Logout")
            logout_action.clicked.connect(self._on_logout)
            self._user_menu.addAction("Logout")

            if is_admin():
                self._user_menu.addSeparator()
                manage_users = self._user_menu.addAction("Manage Users")
                manage_users.triggered.connect(self._show_user_management)
        else:
            login_action = QPushButton("Login")
            login_action.clicked.connect(self._on_login)
            self._user_menu.addAction("Login")

    def _on_login(self):
        if show_login_dialog(self):
            self._update_user_menu()
            self.statusBar().showMessage("Login successful")

    def _on_logout(self):
        if show_logout_dialog(self):
            self._update_user_menu()
            self.statusBar().showMessage("Logged out")

    def _show_user_management(self):
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
        self._camera_page = CameraPage()
        self._detection_page = DetectionPage()
        self._pipeline_page = PipelinePage()
        self._history_page = HistoryPage()
        self._settings_page = SettingsPage()
        self._about_page = AboutPage()

        pages = [
            ("dashboard", self._dashboard_page),
            ("cameras", self._camera_page),
            ("ocr", PlaceholderPage("OCR", "OCR is integrated into the Detection workflow using the old EasyOCR-based backend.")),
            ("detection", self._detection_page),
            ("pipeline", self._pipeline_page),
            ("history", self._history_page),
            ("settings", self._settings_page),
            ("about", self._about_page),
        ]

        self._page_widgets: dict[str, QWidget] = {}
        for page_id, widget in pages:
            self._stack.addWidget(widget)
            self._page_widgets[page_id] = widget

        self._camera_page.camera_added.connect(self._on_camera_added)
        self._camera_page.camera_removed.connect(self._on_camera_removed)
        self._settings_page.settings_changed.connect(self._on_settings_changed)

        self._switch_page("dashboard")
        self.statusBar().showMessage("Ready")

    def _on_camera_added(self, index: int, worker):
        worker.frame_ready.connect(self._detection_page.on_frame_ready)
        self._detection_page.register_camera(index)

    def _on_camera_removed(self, index: int):
        self._detection_page.unregister_camera(index)

    def _on_settings_changed(self, settings: dict):
        self._detection_page.apply_runtime_settings(settings)
        self._pipeline_page.refresh()
        self._about_page.refresh()

    def _switch_page(self, page_id: str):
        widget = self._page_widgets.get(page_id)
        if not widget:
            return
        self._stack.setCurrentWidget(widget)
        if page_id == "dashboard":
            self._dashboard_page.refresh()
        elif page_id == "history":
            self._history_page.refresh()
        elif page_id == "pipeline":
            self._pipeline_page.refresh()
        elif page_id == "about":
            self._about_page.refresh()
        self.statusBar().showMessage(page_id.upper())
