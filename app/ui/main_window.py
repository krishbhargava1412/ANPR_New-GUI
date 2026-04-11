from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
    QSizePolicy, QSpacerItem, QFileDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from app.ui.sidebar import Sidebar
from app.camera.camera_page import CameraPage
from app.detection.detection_page import DetectionPage


class DropZone(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("DROP IMAGE OR VIDEO HERE\n\nor click to browse")
        self.setMinimumHeight(220)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("border-color: #e8ff00; color: #e8ff00;")

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("")
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.setText(f"LOADED\n\n{path.split('/')[-1]}")

    def mousePressEvent(self, event):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "Images & Videos (*.png *.jpg *.jpeg *.bmp *.mp4 *.avi *.mov)"
        )
        if path:
            self.setText(f"LOADED\n\n{path.split('/')[-1]}")


def _stat_card(value: str, label: str, accent: str = "") -> QWidget:
    card = QWidget()
    card.setObjectName("statCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(4)

    val = QLabel(value)
    val.setObjectName("statValue")
    layout.addWidget(val)

    lbl = QLabel(label)
    lbl.setObjectName("statLabel")
    layout.addWidget(lbl)

    if accent:
        acc = QLabel(accent)
        acc.setObjectName("statAccent")
        layout.addWidget(acc)

    return card


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


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(28)

        header = _page_header("Dashboard", "System overview and quick actions")
        layout.addLayout(header)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        stats_row.addWidget(_stat_card("0", "IMAGES PROCESSED", "+ 0 TODAY"))
        stats_row.addWidget(_stat_card("0", "DETECTIONS MADE", "YOLOV8"))
        stats_row.addWidget(_stat_card("0", "OCR EXTRACTIONS", "TESSERACT"))
        stats_row.addWidget(_stat_card("0 ms", "AVG INFERENCE", "PER FRAME"))
        layout.addLayout(stats_row)

        drop_label = QLabel("QUICK PROCESS")
        drop_label.setObjectName("sectionLabel")
        layout.addWidget(drop_label)
        layout.addSpacing(4)

        drop_zone = DropZone()
        layout.addWidget(drop_zone)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        run_btn = QPushButton("RUN PIPELINE")
        run_btn.setObjectName("primaryButton")
        run_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        ocr_btn = QPushButton("OCR ONLY")
        ocr_btn.setObjectName("secondaryButton")
        ocr_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        detect_btn = QPushButton("DETECT ONLY")
        detect_btn.setObjectName("secondaryButton")
        detect_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_row.addWidget(run_btn)
        btn_row.addWidget(ocr_btn)
        btn_row.addWidget(detect_btn)
        btn_row.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addLayout(btn_row)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(28)

        header = _page_header(title, subtitle)
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)

        placeholder = QLabel("NOT YET IMPLEMENTED")
        placeholder.setObjectName("pageSubtitle")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(placeholder)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision — OCR + YOLOv8")
        self.setMinimumSize(QSize(960, 620))
        self._build_ui()

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

        # Instantiate pages
        self._detection_page = DetectionPage()
        self._camera_page = CameraPage()

        pages = [
            ("dashboard", DashboardPage()),
            ("cameras", self._camera_page),
            ("detection", self._detection_page),
            ("ocr", PlaceholderPage(title="OCR", subtitle="Extract text from images using Tesseract")),
            ("pipeline", PlaceholderPage(title="Pipeline", subtitle="Chain OCR and detection in a single pass")),
            ("history", PlaceholderPage(title="History", subtitle="Browse past inference results")),
            ("settings", PlaceholderPage(title="Settings", subtitle="Configure models, paths, and thresholds")),
            ("about", PlaceholderPage(title="About", subtitle="Application info and licenses")),
        ]

        self._page_widgets = {}
        for page_id, widget in pages:
            self._stack.addWidget(widget)
            self._page_widgets[page_id] = widget

        # Wire CameraPage worker signals into DetectionPage
        self._camera_page.camera_added.connect(self._on_camera_added)
        self._camera_page.camera_removed.connect(self._on_camera_removed)

        self._switch_page("dashboard")
        self.statusBar().showMessage("Ready")

    def _on_camera_added(self, index: int, worker):
        """Forward frames from a new CameraWorker to DetectionPage."""
        worker.frame_ready.connect(self._detection_page.on_frame_ready)
        self._detection_page.register_camera(index)

    def _on_camera_removed(self, index: int):
        self._detection_page.unregister_camera(index)

    def _switch_page(self, page_id: str):
        widget = self._page_widgets.get(page_id)
        if widget:
            self._stack.setCurrentWidget(widget)
            self.statusBar().showMessage(page_id.upper())
