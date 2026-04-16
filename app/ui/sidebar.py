from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame, QSpacerItem, QSizePolicy, QStyle, QHBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)
    user_menu_requested = pyqtSignal(object)

    NAV_ITEMS = [
        ("DASHBOARD", "dashboard"),
        ("DETECTION", "detection"),
        ("HISTORY", "history"),
        ("WATCHLIST", "watchlist"),
    ]

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
        self._title_label = title

        subtitle = QLabel("ANPR COMMAND CENTER")
        subtitle.setObjectName("appSubtitle")
        layout.addWidget(subtitle)
        self._subtitle_label = subtitle

        layout.addSpacing(32)

        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("sectionLabel")
        layout.addWidget(nav_label)
        layout.addSpacing(8)

        for label, page_id in self.NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self._account_button.setMinimumHeight(64)
        account_layout = QHBoxLayout(self._account_button)
        account_layout.setContentsMargins(12, 10, 12, 10)
        account_layout.setSpacing(12)
        account_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

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
        text_button_layout.setSpacing(1)

        self._user_name_label = QLabel("Not signed in")
        self._user_name_label.setObjectName("panelTitle")
        self._user_name_label.setWordWrap(False)
        self._user_role_label = QLabel("Guest")
        self._user_role_label.setObjectName("pageSubtitle")
        self._user_role_label.setWordWrap(False)
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
        self._version_label = version

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
        role_text = role.title() if role else "Guest"
        detail = f"{role_text}  |  @{username}" if username.strip() else role_text
        self._user_role_label.setText(detail)

    def enforce_rbac(self, is_admin: bool):
        if "settings" in self._buttons:
            self._buttons["settings"].setVisible(is_admin)

    def apply_responsive_layout(self, breakpoint: str, window_width: int):
        if breakpoint == "small":
            self.setFixedWidth(168)
            self._subtitle_label.hide()
            self._version_label.hide()
            self._user_role_label.hide()
            self._avatar_button.setFixedSize(34, 34)
        elif breakpoint == "medium":
            self.setFixedWidth(188)
            self._subtitle_label.show()
            self._version_label.show()
            self._user_role_label.show()
            self._avatar_button.setFixedSize(38, 38)
        else:
            self.setFixedWidth(212)
            self._subtitle_label.show()
            self._version_label.show()
            self._user_role_label.show()
            self._avatar_button.setFixedSize(40, 40)
