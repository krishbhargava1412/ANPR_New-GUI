import numpy as np

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap


class CameraTile(QWidget):
    """
    Displays a single camera feed. Shows a placeholder when no frame has arrived.
    Emits:
        select_requested(camera_index)  — user clicked the tile or the select button
        remove_requested(camera_index)  — user clicked the remove button
    """

    select_requested = pyqtSignal(int)
    remove_requested = pyqtSignal(int)

    def __init__(self, camera_index: int, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._selected = False
        self._has_frame = False
        self.setObjectName("cameraTile")
        self.setMinimumSize(QSize(240, 180))
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # top bar
        top_bar = QWidget()
        top_bar.setObjectName("cameraTileBar")
        top_bar.setFixedHeight(32)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 0, 8, 0)
        top_layout.setSpacing(6)

        self._title = QLabel(f"CAM {self.camera_index}")
        self._title.setObjectName("cameraTileTitle")
        top_layout.addWidget(self._title)

        self._status_dot = QLabel()
        self._status_dot.setObjectName("statusDotInactive")
        self._status_dot.setFixedSize(QSize(7, 7))
        top_layout.addWidget(self._status_dot)

        top_layout.addStretch()

        select_btn = QPushButton("SELECT")
        select_btn.setObjectName("tileSelectButton")
        select_btn.setFixedHeight(20)
        select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        select_btn.clicked.connect(lambda: self.select_requested.emit(self.camera_index))
        top_layout.addWidget(select_btn)

        remove_btn = QPushButton("X")
        remove_btn.setObjectName("tileRemoveButton")
        remove_btn.setFixedSize(QSize(20, 20))
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.camera_index))
        top_layout.addWidget(remove_btn)

        layout.addWidget(top_bar)

        # frame display
        self._frame_label = QLabel()
        self._frame_label.setObjectName("cameraFrameLabel")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setText(f"NO SIGNAL\nCAM {self.camera_index}")
        self._frame_label.setSizePolicy(
            self._frame_label.sizePolicy().horizontalPolicy(),
            self._frame_label.sizePolicy().verticalPolicy()
        )
        layout.addWidget(self._frame_label, stretch=1)

    def update_frame(self, frame: np.ndarray):
        if not self._has_frame:
            self._has_frame = True
            self._status_dot.setObjectName("statusDotActive")
            self._status_dot.style().unpolish(self._status_dot)
            self._status_dot.style().polish(self._status_dot)

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
        pixmap = QPixmap.fromImage(qt_image)
        scaled = pixmap.scaled(
            self._frame_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self._frame_label.setPixmap(scaled)

    def set_error(self, message: str):
        self._status_dot.setObjectName("statusDotError")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self._frame_label.setText(f"ERROR\n{message}")

    def set_selected(self, selected: bool):
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.select_requested.emit(self.camera_index)
        super().mousePressEvent(event)
