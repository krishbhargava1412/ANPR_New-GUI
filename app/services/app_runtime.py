from __future__ import annotations

import csv
import importlib.util
import json
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from app.storage import (
    get_snapshots_dir,
    get_logs_dir,
    get_watchlist_path,
    get_plate_log_path,
    ensure_storage_dirs,
    get_db_path,
    get_easyocr_dir,
)

from app.detection.legacy_backend import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ensure_runtime_dirs,
    loaded_model_path,
)


OUTPUTS_DIR = get_snapshots_dir()
OUTPUT_LOG_DIR = get_logs_dir()
OCR_DIR = get_easyocr_dir()
SNAPSHOT_DIR = get_snapshots_dir()
WATCHLIST_PATH = get_watchlist_path()
PLATE_LOG_PATH = get_plate_log_path()

OUTPUT_CSV_DIR = get_logs_dir() / "csv"
OUTPUT_VIDEO_DIR = get_logs_dir() / "videos"
SETTINGS_PATH = get_logs_dir() / "ui_settings.json"
APP_LOG_PATH = get_logs_dir() / "anpr_app.log"

APP_ROOT = Path(__file__).resolve().parents[2]
OLD_REPO_ROOT = APP_ROOT.parent / "DRDO_PROJECT" / "ANPD"
OLD_BATCH_ENTRY = OLD_REPO_ROOT / "src" / "anpr_system" / "main.py"
OLD_VISUALIZE_ENTRY = OLD_REPO_ROOT / "src" / "anpr_system" / "visualize.py"
OLD_INTERPOLATE_ENTRY = OLD_REPO_ROOT / "src" / "anpr_system" / "add_missing_data.py"

DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
    "frame_skip": 5,
    "save_snapshots": True,
    "watchlist_alerts_enabled": True,
}


def ensure_app_dirs() -> None:
    ensure_storage_dirs()
    OUTPUT_CSV_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)


def load_ui_settings() -> dict[str, Any]:
    ensure_app_dirs()
    if not SETTINGS_PATH.exists():
        return DEFAULT_UI_SETTINGS.copy()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_UI_SETTINGS.copy()
    merged = DEFAULT_UI_SETTINGS.copy()
    merged.update(
        {key: value for key, value in data.items() if key in DEFAULT_UI_SETTINGS}
    )
    return merged


def save_ui_settings(settings: dict[str, Any]) -> dict[str, Any]:
    ensure_app_dirs()
    merged = DEFAULT_UI_SETTINGS.copy()
    merged.update(settings)
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged


def open_in_shell(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def parse_plate_log_row(row: list[str]) -> dict[str, Any] | None:
    if len(row) < 2:
        return None
    timestamp = row[0]
    plate = row[1]
    source = row[2] if len(row) > 2 else "Unknown"
    confidence_raw = row[3] if len(row) > 3 else ""
    snapshot = row[4] if len(row) > 4 else ""
    watchlist_hit = (row[5] if len(row) > 5 else "0") == "1"
    try:
        parsed_ts = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        parsed_ts = None
    return {
        "timestamp": timestamp,
        "timestamp_dt": parsed_ts,
        "plate": plate,
        "source": source,
        "confidence": float(confidence_raw) if confidence_raw else None,
        "snapshot_path": snapshot,
        "watchlist_hit": watchlist_hit,
    }


def search_plate_log(
    plate: str = "",
    *,
    source_filter: str = "",
    watchlist_only: bool = False,
    from_date: str = "",
    to_date: str = "",
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not PLATE_LOG_PATH.exists():
        return matches
    plate = plate.upper().strip()
    source_filter = source_filter.upper().strip()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d") if from_date else None
        to_dt = datetime.strptime(to_date, "%Y-%m-%d") if to_date else None
    except ValueError:
        return matches
    with open(PLATE_LOG_PATH, newline="", encoding="utf-8") as file:
        for row in csv.reader(file):
            entry = parse_plate_log_row(row)
            if not entry:
                continue
            if plate and plate not in entry["plate"].upper():
                continue
            if source_filter and source_filter not in entry["source"].upper():
                continue
            if watchlist_only and not entry["watchlist_hit"]:
                continue
            if (
                from_dt
                and entry["timestamp_dt"]
                and entry["timestamp_dt"].date() < from_dt.date()
            ):
                continue
            if (
                to_dt
                and entry["timestamp_dt"]
                and entry["timestamp_dt"].date() > to_dt.date()
            ):
                continue
            matches.append(entry)
    return matches


def clear_plate_log() -> None:
    if PLATE_LOG_PATH.exists():
        PLATE_LOG_PATH.unlink()


def clear_outputs() -> int:
    count = 0
    if SNAPSHOT_DIR.exists():
        for f in SNAPSHOT_DIR.glob("*.png"):
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
    return count


def dashboard_stats() -> dict[str, str]:
    ensure_app_dirs()
    detections = search_plate_log()
    unique_plates = len({entry["plate"] for entry in detections})
    watchlist_hits = sum(1 for entry in detections if entry["watchlist_hit"])
    snapshot_count = (
        len(list(SNAPSHOT_DIR.glob("*.png"))) if SNAPSHOT_DIR.exists() else 0
    )
    latest = detections[-1]["timestamp"] if detections else "No detections yet"
    return {
        "detections": str(len(detections)),
        "plates": str(unique_plates),
        "snapshots": str(snapshot_count),
        "watchlist_hits": str(watchlist_hits),
        "latest": latest,
    }


def dependency_status() -> dict[str, str]:
    ensure_app_dirs()
    try:
        model_path = Path(loaded_model_path())
    except FileNotFoundError as exc:
        model_path = Path(str(exc))
    packages = {
        "opencv": importlib.util.find_spec("cv2") is not None,
        "easyocr": importlib.util.find_spec("easyocr") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "ultralytics": importlib.util.find_spec("ultralytics") is not None,
    }
    device = "CPU"
    torch_message = "torch not installed"
    if packages["torch"]:
        import torch

        if torch.cuda.is_available():
            device = f"CUDA ({torch.cuda.get_device_name(0)})"
        else:
            mps = getattr(torch.backends, "mps", None)
            if mps is not None and torch.backends.mps.is_available():
                device = "MPS"
        torch_message = f"torch {torch.__version__}"

    return {
        "model_path": str(model_path),
        "model_exists": "Yes" if model_path.exists() else "No",
        "ocr_cache": str(OCR_DIR),
        "device": device,
        "torch": torch_message,
        "opencv": "Installed" if packages["opencv"] else "Missing",
        "easyocr": "Installed" if packages["easyocr"] else "Missing",
        "ultralytics": "Installed" if packages["ultralytics"] else "Missing",
        "plate_log": str(PLATE_LOG_PATH),
        "watchlist": str(WATCHLIST_PATH),
        "outputs": str(OUTPUTS_DIR),
        "pipeline_batch": "Ready" if OLD_BATCH_ENTRY.exists() else "Missing",
        "pipeline_visualize": "Ready" if OLD_VISUALIZE_ENTRY.exists() else "Missing",
        "pipeline_interpolate": "Ready"
        if OLD_INTERPOLATE_ENTRY.exists()
        else "Missing",
    }
