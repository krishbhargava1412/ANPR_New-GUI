"""Detection orchestrator — client-driven, JS frontend pushes frames via WebSocket."""

from __future__ import annotations

import asyncio
import logging
import time
from threading import Lock
from typing import Any, Optional

import numpy as np

from app.detection.legacy_backend import (
    append_plate_log,
    save_plate_snapshot,
)
from app.detection.plate_pipeline import DetectedBox, PlatePipeline, PlateResult
from app.services.app_runtime import load_ui_settings

LOGGER = logging.getLogger("anpr_new_gui.detection.manager")


class DetectionManager:
    """Manages per-camera detection pipelines.

    Frames are pushed by the JS frontend over WebSocket.
    The backend never opens a camera device directly.
    """

    def __init__(self):
        # camera_id → PlatePipeline
        self._pipelines: dict[int, PlatePipeline] = {}
        # camera_id → conn_id of the client who owns it
        self._owners: dict[int, str] = {}
        # camera_id → set of camera_ids being managed by that client
        self._client_cameras: dict[str, set[int]] = {}
        # camera_id → bool (sharing enabled)
        self._shared_cameras: set[int] = set()

        self._lock = Lock()
        self._running = False
        self._paused = False
        self._frame_skip = 5
        self._frame_counters: dict[int, int] = {}
        self._camera_status: dict[int, str] = {}
        self._latest_results: list[dict[str, Any]] = []
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None

    # ── Event loop ──────────────────────────────────────────────────────────
    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._ws_loop = loop

    # ── Client-camera lifecycle ─────────────────────────────────────────────
    def start_client_camera(
        self, camera_id: int, label: str, conn_id: str,
        loop: asyncio.AbstractEventLoop,
        share: bool = False
    ) -> None:
        """Called when the JS client signals START DETECTION for a camera."""
        self._ws_loop = loop
        settings = load_ui_settings()
        conf = float(settings.get("confidence_threshold", 0.5))
        self._frame_skip = max(1, int(settings.get("frame_skip", 5)))

        with self._lock:
            if camera_id in self._pipelines:
                return  # already running
            if share:
                self._shared_cameras.add(camera_id)
            
        self._start_pipeline(camera_id, conf, label, conn_id)
        with self._lock:
            self._owners[camera_id] = conn_id
            self._client_cameras.setdefault(conn_id, set()).add(camera_id)
        self._running = True
        LOGGER.info("Detection started for camera %d (client: %s)", camera_id, conn_id)

    def stop_client_camera(self, camera_id: int, conn_id: str) -> None:
        self._stop_pipeline(camera_id)
        with self._lock:
            self._owners.pop(camera_id, None)
            if conn_id in self._client_cameras:
                self._client_cameras[conn_id].discard(camera_id)
        LOGGER.info("Detection stopped for camera %d (client: %s)", camera_id, conn_id)

    def pause_client_camera(self, camera_id: int, conn_id: str) -> None:
        with self._lock:
            pipeline = self._pipelines.get(camera_id)
        if pipeline:
            self._paused = not self._paused
            pipeline.set_paused(self._paused)

    def remove_client(self, conn_id: str) -> None:
        """Clean up when a WebSocket connection drops."""
        with self._lock:
            cam_ids = list(self._client_cameras.pop(conn_id, set()))
        for cam_id in cam_ids:
            self._stop_pipeline(cam_id)
            with self._lock:
                self._owners.pop(cam_id, None)
        if cam_ids:
            LOGGER.info("Cleaned up %d camera(s) for disconnected client %s", len(cam_ids), conn_id)

    # ── Frame ingestion (called by WebSocket handler) ───────────────────────
    def submit_frame_from_client(
        self, camera_id: int, frame: np.ndarray, conn_id: str
    ) -> None:
        """Receive a decoded frame from the JS frontend and send to pipeline."""
        with self._lock:
            pipeline = self._pipelines.get(camera_id)
        if pipeline is None:
            return

        self._frame_counters[camera_id] = self._frame_counters.get(camera_id, 0) + 1
        if self._frame_counters[camera_id] % self._frame_skip != 0:
            return

        label = self._camera_status.get(camera_id, f"CAM {camera_id}")
        pipeline.submit_frame(camera_id, frame, label)

    # ── Legacy REST API shims (kept for /api/detection/* compatibility) ─────
    def start_all(self) -> None:
        """Legacy: start detection for all saved camera sources."""
        # In the new architecture this is a no-op;
        # detection is started per-camera by the JS client.
        LOGGER.info("start_all() called — detection is now client-driven")

    def stop_all(self) -> None:
        with self._lock:
            pipeline_ids = list(self._pipelines.keys())
        for cam_id in pipeline_ids:
            self._stop_pipeline(cam_id)
        self._running = False
        self._paused = False
        self._frame_counters.clear()
        LOGGER.info("All detection stopped")

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        with self._lock:
            for pipeline in self._pipelines.values():
                pipeline.set_paused(self._paused)

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._pipelines),
            "paused": self._paused,
            "cameras": dict(self._camera_status),
            "recent_results": self._latest_results[-20:],
        }

    def get_camera_status(self, camera_id: int) -> str:
        return self._camera_status.get(camera_id, "Idle")

    def is_camera_running(self, camera_id: int) -> bool:
        with self._lock:
            return camera_id in self._pipelines

    def is_camera_shared(self, camera_id: int) -> bool:
        with self._lock:
            return camera_id in self._shared_cameras

    # ── Internal pipeline management ────────────────────────────────────────
    def _start_pipeline(self, camera_id: int, confidence: float, label: str, conn_id: str) -> None:
        with self._lock:
            if camera_id in self._pipelines:
                return
        self._camera_status[camera_id] = label
        pipeline = PlatePipeline(
            on_boxes=self._on_boxes_detected,
            on_results=self._on_results,
            on_status=lambda msg, cid=camera_id: self._on_status(cid, msg),
            on_telemetry=self._on_telemetry,
        )
        pipeline.configure(confidence_threshold=confidence)
        with self._lock:
            self._pipelines[camera_id] = pipeline
            self._frame_counters[camera_id] = 0
            self._camera_status[camera_id] = "Loading..."
        pipeline.start()

    def _stop_pipeline(self, camera_id: int) -> None:
        with self._lock:
            pipeline = self._pipelines.pop(camera_id, None)
            self._shared_cameras.discard(camera_id)
        if pipeline:
            pipeline.stop()
        self._camera_status[camera_id] = "Stopped"

    # ── Pipeline callbacks ──────────────────────────────────────────────────
    def _on_boxes_detected(self, camera_id: int, boxes: list[DetectedBox]) -> None:
        self._camera_status[camera_id] = f"Scanning {len(boxes)} plate(s)"
        self._broadcast_json_async({
            "type": "boxes",
            "camera_id": camera_id,
            "count": len(boxes),
            "boxes": [
                {"bbox": list(b.bbox), "confidence": b.confidence}
                for b in boxes
            ],
        })

    def _on_results(self, results: list[PlateResult]) -> None:
        for result in results:
            snapshot_id = None
            settings = load_ui_settings()
            if bool(settings.get("save_snapshots", True)) and result.plate_crop is not None:
                snapshot_id = save_plate_snapshot(
                    result.plate_crop,
                    result.text,
                    result.source,
                )

            append_plate_log(
                result.text,
                source=result.source,
                confidence=result.confidence,
                snapshot_id=snapshot_id,
                watchlist_hit=result.watchlist_hit,
            )

            result_dict = {
                "type": "detection",
                "camera_id": result.camera_index,
                "plate": result.text,
                "confidence": result.confidence,
                "bbox": list(result.bbox),
                "watchlist_hit": result.watchlist_hit,
                "timestamp": result.timestamp,
                "source": result.source,
                "snapshot_id": snapshot_id,
            }
            self._latest_results.append(result_dict)
            self._latest_results = self._latest_results[-50:]
            self._broadcast_json_async(result_dict)

            if result.watchlist_hit:
                self._broadcast_json_async({
                    "type": "alert",
                    "plate": result.text,
                    "camera_id": result.camera_index,
                    "source": result.source,
                    "timestamp": result.timestamp,
                    "snapshot_id": snapshot_id,
                })

            self._camera_status[result.camera_index] = f"Detected {result.text}"

    def _on_status(self, camera_id: int, message: str) -> None:
        self._camera_status[camera_id] = message
        self._broadcast_json_async({
            "type": "status",
            "camera_id": camera_id,
            "message": message,
        })

    def _on_telemetry(self, camera_id: int, payload: dict) -> None:
        self._broadcast_json_async({
            "type": "telemetry",
            "camera_id": camera_id,
            **payload,
        })

    def _broadcast_json_async(self, data: dict) -> None:
        try:
            from app.server.websocket_manager import manager
            if self._ws_loop and not self._ws_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast_json(data),
                    self._ws_loop,
                )
        except Exception:
            pass
