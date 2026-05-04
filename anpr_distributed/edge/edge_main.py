"""
Main entry point for the Jetson edge node.

Orchestrates:
  1. Camera ingestion (4 streams)
  2. Inference engine (YOLOv8 + PaddleOCR)
  3. Plate vote tracking + temporal deduplication
  4. Local watchlist cache (for instant alerts)
  5. Store-and-forward buffer (for network resilience)
  6. Heartbeat reporting to DRDO server
  7. Thermal throttling management

This script runs COMPLETELY HEADLESS — no GUI, no PyQt6.
"""
from __future__ import annotations

import logging
import signal
import subprocess
import threading
import time
import sys
from datetime import datetime
from pathlib import Path

# Ensure shared package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edge.config import (
    HEARTBEAT_INTERVAL_SECONDS,
    NORMAL_FPS,
    SAVE_SNAPSHOTS,
    SNAPSHOTS_DIR,
    THERMAL_CHECK_INTERVAL,
    THERMAL_THROTTLE_FPS,
    THERMAL_THROTTLE_TEMP,
    parse_camera_sources,
    EDGE_NODE_ID,
    SERVER_URL,
    EDGE_API_KEY,
)
from edge.ingestion import IngestionManager
from edge.inference import InferenceEngine
from edge.plate_processing import PlateVoteTracker, TemporalDeduplicator
from edge.store_forward import StoreAndForward
from edge.watchlist_cache import WatchlistCache

import cv2
import numpy as np
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("anpr.edge.main")

# ── Globals ───────────────────────────────────────────────────────────────────
_shutdown_event = threading.Event()


def signal_handler(sig, frame):
    LOGGER.info("Shutdown signal received.")
    _shutdown_event.set()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ── Thermal Monitoring ────────────────────────────────────────────────────────
def read_gpu_temperature() -> float | None:
    """Read Jetson GPU temperature from tegrastats or thermal zone."""
    # Method 1: thermal zone file (works on all Jetsons)
    thermal_zones = [
        "/sys/devices/virtual/thermal/thermal_zone1/temp",  # GPU on most Jetsons
        "/sys/devices/virtual/thermal/thermal_zone2/temp",
    ]
    for zone in thermal_zones:
        try:
            temp = int(Path(zone).read_text().strip()) / 1000.0
            return temp
        except (FileNotFoundError, ValueError):
            continue

    # Method 2: nvidia-smi (desktop GPU fallback)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    return None


def thermal_monitor_loop(ingestion: IngestionManager):
    """Background thread that throttles FPS when GPU overheats."""
    throttled = False
    while not _shutdown_event.is_set():
        temp = read_gpu_temperature()
        if temp is not None:
            if temp >= THERMAL_THROTTLE_TEMP and not throttled:
                LOGGER.warning(
                    "GPU temperature %.1f°C exceeds threshold (%.1f°C). "
                    "Throttling to %d FPS.",
                    temp, THERMAL_THROTTLE_TEMP, THERMAL_THROTTLE_FPS,
                )
                ingestion.set_all_fps(THERMAL_THROTTLE_FPS)
                throttled = True
            elif temp < THERMAL_THROTTLE_TEMP - 5 and throttled:
                LOGGER.info(
                    "GPU temperature %.1f°C recovered. Restoring %d FPS.",
                    temp, NORMAL_FPS,
                )
                ingestion.set_all_fps(NORMAL_FPS)
                throttled = False

        _shutdown_event.wait(THERMAL_CHECK_INTERVAL)


# ── Heartbeat ─────────────────────────────────────────────────────────────────
def heartbeat_loop(ingestion: IngestionManager, start_time: float, stats: dict):
    """Send periodic heartbeats to the DRDO server."""
    while not _shutdown_event.is_set():
        temp = read_gpu_temperature()
        payload = {
            "edge_node_id": EDGE_NODE_ID,
            "active_cameras": len(ingestion.streams),
            "gpu_temp_celsius": temp,
            "uptime_seconds": time.time() - start_time,
            "inference_fps": stats.get("fps", 0.0),
            "queue_depth": stats.get("queue_depth", 0),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            requests.post(
                f"{SERVER_URL}/api/edge/heartbeat",
                json=payload,
                headers={"X-Edge-API-Key": EDGE_API_KEY},
                timeout=5,
            )
        except Exception:
            pass  # Heartbeat failure is non-critical

        _shutdown_event.wait(HEARTBEAT_INTERVAL_SECONDS)


# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    LOGGER.info("=" * 60)
    LOGGER.info("  ANPR Edge Node Starting — %s", EDGE_NODE_ID)
    LOGGER.info("=" * 60)

    # 1. Parse camera sources
    camera_configs = parse_camera_sources()
    if not camera_configs:
        LOGGER.error("No cameras configured. Set CAMERA_SOURCES env var.")
        sys.exit(1)
    LOGGER.info("Configured %d camera(s): %s",
                len(camera_configs),
                [c["label"] for c in camera_configs])

    # 2. Initialize components
    ingestion = IngestionManager(camera_configs)
    engine = InferenceEngine()
    vote_tracker = PlateVoteTracker()
    deduplicator = TemporalDeduplicator()
    store_forward = StoreAndForward()
    watchlist_cache = WatchlistCache()

    # 3. Load ML models
    LOGGER.info("Loading ML models...")
    try:
        engine.load_models()
    except Exception as exc:
        LOGGER.error("Failed to load models: %s", exc)
        sys.exit(1)

    # 4. Start all services
    ingestion.start_all()
    store_forward.start_push_loop()
    watchlist_cache.start_sync()

    # 5. Start background threads
    stats = {"fps": 0.0, "queue_depth": 0}
    start_time = time.time()

    thermal_thread = threading.Thread(
        target=thermal_monitor_loop, args=(ingestion,),
        name="thermal-monitor", daemon=True,
    )
    thermal_thread.start()

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop, args=(ingestion, start_time, stats),
        name="heartbeat", daemon=True,
    )
    heartbeat_thread.start()

    LOGGER.info("All services started. Entering detection loop...")

    # 6. Main detection loop
    frame_count = 0
    fps_timer = time.time()

    while not _shutdown_event.is_set():
        # Get latest frames from all cameras
        frames = ingestion.get_latest_frames()

        if not frames:
            time.sleep(0.01)
            continue

        for camera_id, (frame, frame_id) in frames.items():
            # Run inference
            detections = engine.detect_plates(frame)

            for det in detections:
                plate_text = det.get("plate_text")
                if not plate_text:
                    continue

                # Vote tracking — confirm plate
                stable_text = vote_tracker.register(
                    camera_id,
                    det["bbox"],
                    plate_text,
                    det.get("confidence", 0.0),
                )
                if not stable_text:
                    continue

                # Temporal deduplication
                if deduplicator.is_duplicate(camera_id, stable_text):
                    continue

                # Watchlist check (local cache — instant)
                watchlist_hit = watchlist_cache.is_watchlist_hit(stable_text)

                if watchlist_hit:
                    LOGGER.warning(
                        "🚨 WATCHLIST HIT: %s on %s (conf=%.2f)",
                        stable_text, camera_id, det.get("confidence", 0),
                    )

                # Save snapshot locally
                snapshot_crop = det.get("plate_crop")
                if SAVE_SNAPSHOTS and snapshot_crop is not None:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = SNAPSHOTS_DIR / f"{camera_id}_{stable_text}_{ts}.jpg"
                    cv2.imwrite(str(path), snapshot_crop)

                # Buffer for server push
                store_forward.buffer_detection(
                    camera_id=camera_id,
                    plate_number=stable_text,
                    confidence=det.get("confidence", 0.0),
                    ocr_score=det.get("ocr_score", 0.0),
                    bbox=det["bbox"],
                    plate_crop=snapshot_crop,
                    watchlist_hit=watchlist_hit,
                )

                LOGGER.info(
                    "✅ Plate: %-12s | Camera: %-8s | Conf: %.2f | WL: %s",
                    stable_text, camera_id,
                    det.get("confidence", 0), "YES" if watchlist_hit else "no",
                )

            frame_count += 1

        # FPS calculation
        elapsed = time.time() - fps_timer
        if elapsed >= 5.0:
            stats["fps"] = frame_count / elapsed
            stats["queue_depth"] = store_forward.pending_count()
            LOGGER.info(
                "📊 FPS: %.1f | Cameras: %d | Buffer: %d pending",
                stats["fps"], len(frames), stats["queue_depth"],
            )
            frame_count = 0
            fps_timer = time.time()

    # 7. Graceful shutdown
    LOGGER.info("Shutting down edge node...")
    ingestion.stop_all()
    store_forward.stop()
    watchlist_cache.stop()
    LOGGER.info("Edge node stopped.")


if __name__ == "__main__":
    main()
