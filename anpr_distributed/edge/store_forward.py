"""
Store-and-forward buffer for network resilience.

If the DRDO server is unreachable, detections are stored in a local SQLite
database on the Jetson. A background thread periodically attempts to push
buffered detections to the server and clears them on success.

This ensures zero data loss during network outages.
"""
from __future__ import annotations

import base64
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import requests

from edge.config import (
    BATCH_PUSH_INTERVAL_SECONDS,
    EDGE_API_KEY,
    EDGE_NODE_ID,
    LOCAL_DB_PATH,
    MAX_LOCAL_BUFFER_SIZE,
    SERVER_URL,
)

LOGGER = logging.getLogger("anpr.edge.store_forward")


class StoreAndForward:
    """
    Local SQLite buffer + background pusher.
    Thread-safe: multiple camera threads can call buffer_detection() concurrently.
    """

    def __init__(self):
        self._db_path = str(LOCAL_DB_PATH)
        self._lock = threading.Lock()
        self._running = False
        self._push_thread: Optional[threading.Thread] = None
        self._init_db()

    def _init_db(self) -> None:
        """Create the local buffer table if it doesn't exist."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detection_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    plate_number TEXT NOT NULL,
                    confidence REAL,
                    ocr_score REAL,
                    bbox TEXT,
                    snapshot_b64 TEXT,
                    detected_at TEXT NOT NULL,
                    watchlist_hit INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def buffer_detection(
        self,
        camera_id: str,
        plate_number: str,
        confidence: float,
        ocr_score: float,
        bbox: tuple[int, int, int, int],
        plate_crop: Optional[np.ndarray] = None,
        watchlist_hit: bool = False,
        detected_at: Optional[datetime] = None,
    ) -> None:
        """Add a detection to the local buffer. Thread-safe."""
        snapshot_b64 = None
        if plate_crop is not None:
            try:
                _, buffer = cv2.imencode(".jpg", plate_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
                snapshot_b64 = base64.b64encode(buffer).decode("utf-8")
            except Exception:
                pass

        ts = (detected_at or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO detection_buffer
                       (camera_id, plate_number, confidence, ocr_score, bbox,
                        snapshot_b64, detected_at, watchlist_hit)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        camera_id,
                        plate_number,
                        confidence,
                        ocr_score,
                        json.dumps(list(bbox)),
                        snapshot_b64,
                        ts,
                        1 if watchlist_hit else 0,
                    ),
                )
                conn.commit()

                # Enforce max buffer size (delete oldest)
                count = conn.execute("SELECT COUNT(*) FROM detection_buffer").fetchone()[0]
                if count > MAX_LOCAL_BUFFER_SIZE:
                    excess = count - MAX_LOCAL_BUFFER_SIZE
                    conn.execute(
                        f"DELETE FROM detection_buffer WHERE id IN "
                        f"(SELECT id FROM detection_buffer ORDER BY id ASC LIMIT {excess})"
                    )
                    conn.commit()

    def start_push_loop(self) -> None:
        """Start the background thread that pushes buffered data to the server."""
        self._running = True
        self._push_thread = threading.Thread(
            target=self._push_loop, name="store-forward-push", daemon=True,
        )
        self._push_thread.start()
        LOGGER.info("Store-and-forward push loop started (interval=%ds).",
                     BATCH_PUSH_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False
        if self._push_thread:
            self._push_thread.join(timeout=10)

    def pending_count(self) -> int:
        """How many detections are waiting to be pushed."""
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                return conn.execute("SELECT COUNT(*) FROM detection_buffer").fetchone()[0]

    def _push_loop(self) -> None:
        """Periodically push buffered detections to the server."""
        while self._running:
            try:
                self._push_batch()
            except Exception as exc:
                LOGGER.debug("Push attempt failed: %s", exc)
            time.sleep(BATCH_PUSH_INTERVAL_SECONDS)

    def _push_batch(self) -> None:
        """Attempt to push a batch of detections to the DRDO server."""
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT id, camera_id, plate_number, confidence, ocr_score, "
                    "bbox, snapshot_b64, detected_at, watchlist_hit "
                    "FROM detection_buffer ORDER BY id ASC LIMIT 50"
                ).fetchall()

        if not rows:
            return

        detections = []
        row_ids = []
        for row in rows:
            row_ids.append(row[0])
            detections.append({
                "camera_id": row[1],
                "plate_number": row[2],
                "confidence": row[3] or 0.0,
                "ocr_score": row[4] or 0.0,
                "bbox": json.loads(row[5]) if row[5] else [0, 0, 0, 0],
                "snapshot_b64": row[6],
                "detected_at": row[7],
                "watchlist_hit": bool(row[8]),
                "edge_node_id": EDGE_NODE_ID,
            })

        payload = {
            "detections": detections,
            "edge_node_id": EDGE_NODE_ID,
            "batch_timestamp": datetime.now().isoformat(),
        }

        try:
            resp = requests.post(
                f"{SERVER_URL}/api/edge/detections",
                json=payload,
                headers={"X-Edge-API-Key": EDGE_API_KEY},
                timeout=10,
            )
            if resp.status_code == 200:
                # Delete successfully pushed rows
                with self._lock:
                    with sqlite3.connect(self._db_path) as conn:
                        placeholders = ",".join("?" * len(row_ids))
                        conn.execute(
                            f"DELETE FROM detection_buffer WHERE id IN ({placeholders})",
                            row_ids,
                        )
                        conn.commit()
                LOGGER.info("Pushed %d detections to server. %d remaining.",
                            len(row_ids), self.pending_count())
            else:
                LOGGER.warning("Server returned %d. Will retry.", resp.status_code)
        except requests.ConnectionError:
            LOGGER.debug("Server unreachable. Buffering locally (%d pending).",
                         self.pending_count())
        except requests.Timeout:
            LOGGER.debug("Server timeout. Will retry.")
