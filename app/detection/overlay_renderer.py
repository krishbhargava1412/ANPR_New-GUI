import cv2
import numpy as np

from PyQt6.QtCore import QThread, QMutex, QMutexLocker, pyqtSignal
from PyQt6.QtGui import QImage

_COLOR_SCANNING = (0, 200, 255)
_COLOR_CONFIRMED = (0, 230, 0)
_COLOR_LOW = (0, 208, 255)
_COLOR_ALERT = (32, 32, 255)
_FONT = cv2.FONT_HERSHEY_SIMPLEX

class OverlayRenderer(QThread):
    rendered = pyqtSignal(int, QImage)  # camera_index, finished_image

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._queue = []
        self._running = True

    def enqueue(self, camera_index, frame, boxes, results, source_label):
        with QMutexLocker(self._mutex):
            # Overwrite if camera is already in queue to prevent backpressure
            idx = next((i for i, v in enumerate(self._queue) if v[0] == camera_index), -1)
            item = (camera_index, frame, boxes, results, source_label)
            if idx >= 0:
                self._queue[idx] = item
            else:
                self._queue.append(item)

    def stop(self):
        with QMutexLocker(self._mutex):
            self._running = False
        self.wait()

    def run(self):
        while True:
            with QMutexLocker(self._mutex):
                if not self._running:
                    break
                if not self._queue:
                    item = None
                else:
                    item = self._queue.pop(0)

            if item is None:
                self.msleep(5)
                continue

            camera_index, frame, boxes, results, source_label = item
            out = frame.copy()
            for box in boxes:
                x1, y1, x2, y2 = box.bbox
                cv2.rectangle(out, (x1, y1), (x2, y2), _COLOR_SCANNING, 2)
            for result in results:
                x1, y1, x2, y2 = result.bbox
                color = _COLOR_ALERT if result.watchlist_hit else _COLOR_CONFIRMED
                cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
                label = f"{result.text} | {result.confidence:.2f}"
                (tw, th), _ = cv2.getTextSize(label, _FONT, 0.55, 1)
                bg_y1 = max(0, y1 - th - 8)
                cv2.rectangle(out, (x1, bg_y1), (x1 + tw + 8, y1), color, -1)
                cv2.putText(out, label, (x1 + 4, y1 - 4), _FONT, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
            
            # Convert to QImage immediately off-thread
            h, w, ch = out.shape
            bytes_per_line = ch * w
            qimg = QImage(out.data, w, h, bytes_per_line, QImage.Format.Format_BGR888).copy()
            self.rendered.emit(camera_index, qimg)
