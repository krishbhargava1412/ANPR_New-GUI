from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame, QSpacerItem, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)

    NAV_ITEMS = [
        ("DASHBOARD", "dashboard"),
        ("CAMERAS", "cameras"),
        ("OCR", "ocr"),
        ("DETECTION", "detection"),
        ("PIPELINE", "pipeline"),
        ("HISTORY", "history"),
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

        version = QLabel("v0.1.0")
        version.setObjectName("appSubtitle")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

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
