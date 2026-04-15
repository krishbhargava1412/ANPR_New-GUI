from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame, QSpacerItem, QSizePolicy, QStyle, QHBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)
    user_menu_requested = pyqtSignal(object)

    NAV_ITEMS = [
        ("DASHBOARD", "dashboard"),
        ("DETECTION", "detection"),
        ("HISTORY", "history"),
    ]
    ICON_MAP = {
        "dashboard": QStyle.StandardPixmap.SP_DesktopIcon,
        "detection": QStyle.StandardPixmap.SP_MediaPlay,
        "history": QStyle.StandardPixmap.SP_FileDialogDetailedView,
        "settings": QStyle.StandardPixmap.SP_FileDialogContentsView,
        "about": QStyle.StandardPixmap.SP_MessageBoxInformation,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(200)
        self._active_page = "dashboard"
        self._buttons = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(0)

        title = QLabel("VISION")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        subtitle = QLabel("OCR + YOLO")
        subtitle.setObjectName("appSubtitle")
        layout.addWidget(subtitle)

        layout.addSpacing(32)

        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("sectionLabel")
        layout.addWidget(nav_label)
        layout.addSpacing(8)

        for label, page_id in self.NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(self.style().standardIcon(self.ICON_MAP[page_id]))
            btn.clicked.connect(lambda checked, p=page_id: self._on_nav_click(p))
            self._buttons[page_id] = btn
            layout.addWidget(btn)
            layout.addSpacing(2)

        layout.addSpacing(24)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        layout.addSpacing(24)

        tools_label = QLabel("TOOLS")
        tools_label.setObjectName("sectionLabel")
        layout.addWidget(tools_label)
        layout.addSpacing(8)

        for label, page_id in [("SETTINGS", "settings"), ("ABOUT", "about")]:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(self.style().standardIcon(self.ICON_MAP[page_id]))
            btn.clicked.connect(lambda checked, p=page_id: self._on_nav_click(p))
            self._buttons[page_id] = btn
            layout.addWidget(btn)
            layout.addSpacing(2)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        self._account_button = QFrame()
        self._account_button.setObjectName("sidebarAccountButton")
        self._account_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._account_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        account_layout = QHBoxLayout(self._account_button)
        account_layout.setContentsMargins(10, 10, 10, 10)
        account_layout.setSpacing(10)

        self._avatar_button = QPushButton("U")
        self._avatar_button.setObjectName("avatarButton")
        self._avatar_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._avatar_button.setFixedSize(38, 38)
        self._avatar_button.clicked.connect(lambda: self.user_menu_requested.emit(self._account_button))
        account_layout.addWidget(self._avatar_button)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self._account_text_button = QPushButton()
        self._account_text_button.setObjectName("sidebarAccountTextButton")
        self._account_text_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._account_text_button.clicked.connect(
            lambda: self.user_menu_requested.emit(self._account_button)
        )

        text_button_layout = QVBoxLayout(self._account_text_button)
        text_button_layout.setContentsMargins(0, 0, 0, 0)
        text_button_layout.setSpacing(2)

        self._user_name_label = QLabel("Not signed in")
        self._user_name_label.setObjectName("panelTitle")
        self._user_role_label = QLabel("Guest")
        self._user_role_label.setObjectName("pageSubtitle")
        text_button_layout.addWidget(self._user_name_label)
        text_button_layout.addWidget(self._user_role_label)
        text_layout.addWidget(self._account_text_button)
        account_layout.addLayout(text_layout, 1)

        version = QLabel("v0.1.0")
        version.setObjectName("appSubtitle")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        footer_layout.addWidget(self._account_button)
        footer_layout.addWidget(version)
        layout.addWidget(footer)

        self._set_active("dashboard")

    def _on_nav_click(self, page_id: str):
        self._set_active(page_id)
        self.page_changed.emit(page_id)

    def _set_active(self, page_id: str):
        if self._active_page in self._buttons:
            self._buttons[self._active_page].setProperty("active", False)
            self._buttons[self._active_page].style().unpolish(self._buttons[self._active_page])
            self._buttons[self._active_page].style().polish(self._buttons[self._active_page])

        self._active_page = page_id

        if page_id in self._buttons:
            self._buttons[page_id].setProperty("active", True)
            self._buttons[page_id].style().unpolish(self._buttons[page_id])
            self._buttons[page_id].style().polish(self._buttons[page_id])

    def set_user_info(self, full_name: str, role: str, username: str = ""):
        display_name = full_name.strip() or username.strip() or "Unknown User"
        initials = "".join(part[0].upper() for part in display_name.split()[:2]) or "U"
        self._avatar_button.setText(initials[:2])
        self._user_name_label.setText(display_name)
        self._user_role_label.setText(role.title() if role else "Guest")
