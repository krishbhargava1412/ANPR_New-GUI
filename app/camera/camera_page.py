import math
import cv2

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QComboBox, QFrame, QSizePolicy, QSpacerItem,
    QGridLayout
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from app.camera.camera_worker import CameraWorker
from app.camera.camera_tile import CameraTile


def _probe_cameras(max_index: int = 8) -> list[int]:
    """Return list of camera indices that cv2 can open."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
            cap.release()
    return found


class CameraPage(QWidget):
    """
    Camera management page.

    Signals:
        camera_added(index, worker)   — emitted after a CameraWorker is started
        camera_removed(index)         — emitted after a camera is stopped and removed
    """

    _MAX_GRID_COLS = 3

    camera_added = pyqtSignal(int, object)
    camera_removed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")

        self._workers: dict[int, CameraWorker] = {}
        self._tiles: dict[int, CameraTile] = {}
        self._available_cameras: list[int] = []
        self._selected_index: int | None = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 24)
        root.setSpacing(0)

        # header row
        header_row = QHBoxLayout()
        header_row.setSpacing(0)

        title_block = QVBoxLayout()
        title_block.setSpacing(4)
        title = QLabel("Camera Manager")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Live feeds — add, remove, and select active cameras")
        subtitle.setObjectName("pageSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header_row.addLayout(title_block)
        header_row.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self._scan_btn = QPushButton("SCAN CAMERAS")
        self._scan_btn.setObjectName("primaryButton")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.clicked.connect(self._scan_cameras)
        header_row.addWidget(self._scan_btn)

        root.addLayout(header_row)
        root.addSpacing(24)

        # controls bar
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(10)

        self._camera_combo = QComboBox()
        self._camera_combo.setObjectName("cameraCombo")
        self._camera_combo.setFixedHeight(36)
        self._camera_combo.setMinimumWidth(160)
        self._camera_combo.setPlaceholderText("Select camera")
        ctrl_bar.addWidget(self._camera_combo)

        self._add_btn = QPushButton("ADD TO GRID")
        self._add_btn.setObjectName("secondaryButton")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._add_selected_camera)
        ctrl_bar.addWidget(self._add_btn)

        divider_v = QFrame()
        divider_v.setObjectName("divider")
        divider_v.setFrameShape(QFrame.Shape.VLine)
        divider_v.setFixedWidth(1)
        divider_v.setFixedHeight(28)
        ctrl_bar.addWidget(divider_v)

        self._stop_all_btn = QPushButton("STOP ALL")
        self._stop_all_btn.setObjectName("secondaryButton")
        self._stop_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_all_btn.setEnabled(False)
        self._stop_all_btn.clicked.connect(self._stop_all_cameras)
        ctrl_bar.addWidget(self._stop_all_btn)

        ctrl_bar.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        self._selected_label = QLabel("NO CAMERA SELECTED")
        self._selected_label.setObjectName("pageSubtitle")
        ctrl_bar.addWidget(self._selected_label)

        root.addLayout(ctrl_bar)
        root.addSpacing(20)

        divider_h = QFrame()
        divider_h.setObjectName("divider")
        divider_h.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider_h)
        root.addSpacing(20)

        # grid scroll area
        self._scroll = QScrollArea()
        self._scroll.setObjectName("cameraScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_container = QWidget()
        self._grid_container.setObjectName("cameraGridContainer")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(10)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)

        self._empty_label = QLabel("NO CAMERAS ACTIVE\n\nClick SCAN CAMERAS then ADD TO GRID")
        self._empty_label.setObjectName("dropZone")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setMinimumHeight(300)
        self._grid_layout.addWidget(self._empty_label, 0, 0)

        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, stretch=1)

        root.addSpacing(16)

        # status bar row
        self._status_label = QLabel("Ready — click SCAN CAMERAS to detect connected devices")
        self._status_label.setObjectName("pageSubtitle")
        root.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Camera scanning
    # ------------------------------------------------------------------

    def _scan_cameras(self):
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("SCANNING...")
        self._status_label.setText("Probing camera indices 0-7...")

        # Use QTimer to let the UI repaint before blocking probe
        QTimer.singleShot(50, self._do_probe)

    def _do_probe(self):
        self._available_cameras = _probe_cameras(max_index=8)

        self._camera_combo.clear()
        if self._available_cameras:
            for idx in self._available_cameras:
                label = f"Camera {idx}"
                if idx in self._tiles:
                    label += " (active)"
                self._camera_combo.addItem(label, userData=idx)
            self._add_btn.setEnabled(True)
            self._status_label.setText(f"Found {len(self._available_cameras)} camera(s): indices {self._available_cameras}")
        else:
            self._camera_combo.setPlaceholderText("No cameras found")
            self._add_btn.setEnabled(False)
            self._status_label.setText("No cameras found. Ensure devices are connected and not in use.")

        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("SCAN CAMERAS")

    # ------------------------------------------------------------------
    # Add / remove cameras
    # ------------------------------------------------------------------

    def _add_selected_camera(self):
        idx = self._camera_combo.currentData()
        if idx is None:
            return
        if idx in self._tiles:
            self._status_label.setText(f"Camera {idx} is already in the grid.")
            return
        self._add_camera(idx)

    def _add_camera(self, index: int):
        tile = CameraTile(camera_index=index)
        tile.select_requested.connect(self._on_tile_selected)
        tile.remove_requested.connect(self._remove_camera)
        self._tiles[index] = tile

        self._rebuild_grid()

        worker = CameraWorker(camera_index=index, fps=30)
        worker.frame_ready.connect(self._on_frame_ready)
        worker.error.connect(self._on_camera_error)
        self._workers[index] = worker
        worker.start()

        self._stop_all_btn.setEnabled(True)
        self._status_label.setText(f"Camera {index} added.")
        self._refresh_combo_labels()
        self.camera_added.emit(index, worker)

        if self._selected_index is None:
            self._on_tile_selected(index)

    def _remove_camera(self, index: int):
        if index in self._workers:
            self._workers[index].stop()
            del self._workers[index]

        if index in self._tiles:
            tile = self._tiles.pop(index)
            tile.setParent(None)
            tile.deleteLater()

        self._rebuild_grid()

        if self._selected_index == index:
            self._selected_index = None
            self._selected_label.setText("NO CAMERA SELECTED")
            if self._tiles:
                first = next(iter(self._tiles))
                self._on_tile_selected(first)

        if not self._workers:
            self._stop_all_btn.setEnabled(False)

        self._status_label.setText(f"Camera {index} removed.")
        self._refresh_combo_labels()
        self.camera_removed.emit(index)

    def _stop_all_cameras(self):
        indices = list(self._workers.keys())
        for idx in indices:
            self._remove_camera(idx)
        self._status_label.setText("All cameras stopped.")

    # ------------------------------------------------------------------
    # Grid layout
    # ------------------------------------------------------------------

    def _rebuild_grid(self):
        # remove all widgets from grid without deleting them
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if not self._tiles:
            self._grid_layout.addWidget(self._empty_label, 0, 0)
            self._empty_label.show()
            return

        self._empty_label.hide()

        cols = min(len(self._tiles), self._MAX_GRID_COLS)
        for position, (index, tile) in enumerate(self._tiles.items()):
            row = position // cols
            col = position % cols
            self._grid_layout.addWidget(tile, row, col)
            tile.show()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_tile_selected(self, index: int):
        if self._selected_index is not None and self._selected_index in self._tiles:
            self._tiles[self._selected_index].set_selected(False)

        self._selected_index = index
        if index in self._tiles:
            self._tiles[index].set_selected(True)

        self._selected_label.setText(f"SELECTED: CAM {index}")

    # ------------------------------------------------------------------
    # Frame / error handlers
    # ------------------------------------------------------------------

    def _on_frame_ready(self, index: int, frame):
        if index in self._tiles:
            self._tiles[index].update_frame(frame)

    def _on_camera_error(self, index: int, message: str):
        if index in self._tiles:
            self._tiles[index].set_error(message)
        self._status_label.setText(f"Camera {index} error: {message}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_combo_labels(self):
        for i in range(self._camera_combo.count()):
            idx = self._camera_combo.itemData(i)
            label = f"Camera {idx}"
            if idx in self._tiles:
                label += " (active)"
            self._camera_combo.setItemText(i, label)

    def closeEvent(self, event):
        self._stop_all_cameras()
        super().closeEvent(event)
