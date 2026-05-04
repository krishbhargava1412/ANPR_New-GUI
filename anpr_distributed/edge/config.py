"""
Edge node (Jetson) configuration.

All settings are loaded from environment variables for headless deployment.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── DRDO Server Connection ────────────────────────────────────────────────────
SERVER_URL = os.environ.get("ANPR_SERVER_URL", "http://192.168.1.100:8000")
EDGE_API_KEY = os.environ.get("EDGE_API_KEY", "edge-jetson-key-change-in-prod")
EDGE_NODE_ID = os.environ.get("EDGE_NODE_ID", "jetson-01")

# ── Camera Sources ────────────────────────────────────────────────────────────
# Comma-separated RTSP URLs or device indices
# Example: "rtsp://admin:pass@192.168.1.10:554/stream1,rtsp://admin:pass@192.168.1.11:554/stream1"
CAMERA_SOURCES_RAW = os.environ.get("CAMERA_SOURCES", "0")

def parse_camera_sources() -> list[dict]:
    """Parse camera sources from environment variable."""
    sources = []
    for idx, raw in enumerate(CAMERA_SOURCES_RAW.split(",")):
        raw = raw.strip()
        if not raw:
            continue
        try:
            source = int(raw)
            kind = "usb"
        except ValueError:
            source = raw
            kind = "rtsp"
        sources.append({
            "id": f"cam_{idx + 1}",
            "source": source,
            "kind": kind,
            "label": f"Camera {idx + 1}",
        })
    return sources


# ── Inference Settings ────────────────────────────────────────────────────────
MODEL_PATH = os.environ.get(
    "YOLO_MODEL_PATH",
    str(Path(__file__).parent.parent / "assets" / "models" / "LicensePlateDetector.pt"),
)
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.5"))
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "5"))
PROXY_RESOLUTION_ENABLED = os.environ.get("PROXY_RESOLUTION", "true").lower() == "true"
INFERENCE_BATCH_SIZE = int(os.environ.get("INFERENCE_BATCH_SIZE", "4"))
USE_TENSORRT = os.environ.get("USE_TENSORRT", "false").lower() == "true"

# ── Store & Forward ──────────────────────────────────────────────────────────
LOCAL_DB_PATH = Path(os.environ.get("LOCAL_DB_PATH", "./data/edge_buffer.db"))
LOCAL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
BATCH_PUSH_INTERVAL_SECONDS = int(os.environ.get("BATCH_PUSH_INTERVAL", "5"))
MAX_LOCAL_BUFFER_SIZE = int(os.environ.get("MAX_LOCAL_BUFFER", "10000"))

# ── Watchlist Cache ──────────────────────────────────────────────────────────
WATCHLIST_SYNC_INTERVAL_SECONDS = int(os.environ.get("WATCHLIST_SYNC_INTERVAL", "60"))

# ── Thermal Management ───────────────────────────────────────────────────────
THERMAL_CHECK_INTERVAL = int(os.environ.get("THERMAL_CHECK_INTERVAL", "10"))
THERMAL_THROTTLE_TEMP = float(os.environ.get("THERMAL_THROTTLE_TEMP", "80.0"))
THERMAL_THROTTLE_FPS = int(os.environ.get("THERMAL_THROTTLE_FPS", "5"))
NORMAL_FPS = int(os.environ.get("NORMAL_FPS", "15"))

# ── Heartbeat ─────────────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL_SECONDS = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))

# ── Snapshot Settings ────────────────────────────────────────────────────────
SNAPSHOTS_DIR = Path(os.environ.get("SNAPSHOTS_DIR", "./data/snapshots"))
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
SAVE_SNAPSHOTS = os.environ.get("SAVE_SNAPSHOTS", "true").lower() == "true"

# ── OCR Settings ──────────────────────────────────────────────────────────────
OCR_DIR = Path(os.environ.get(
    "OCR_DIR",
    str(Path(__file__).parent.parent / "assets" / "awiros_anpr"),
))
