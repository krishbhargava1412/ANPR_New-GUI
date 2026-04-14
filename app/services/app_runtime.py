from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import json
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
    get_awiros_anpr_dir,
)

from app.detection.legacy_backend import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PADDLEOCR_SOURCE_DIR,
    _prepare_paddle_windows_runtime,
    current_runtime_devices,
    ensure_runtime_dirs,
    loaded_model_path,
)


OUTPUTS_DIR = get_snapshots_dir()
OUTPUT_LOG_DIR = get_logs_dir()
OCR_DIR = get_awiros_anpr_dir()
SNAPSHOT_DIR = get_snapshots_dir()
WATCHLIST_PATH = get_watchlist_path()
PLATE_LOG_PATH = get_plate_log_path()

OUTPUT_CSV_DIR = get_logs_dir() / "csv"
OUTPUT_VIDEO_DIR = get_logs_dir() / "videos"
SETTINGS_PATH = get_logs_dir() / "ui_settings.json"
APP_LOG_PATH = get_logs_dir() / "anpr_app.log"

APP_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
    "frame_skip": 5,
    "save_snapshots": True,
    "watchlist_alerts_enabled": True,
    "camera_indices": "",
    "default_camera": -1,
    "auto_start_cameras": False,
    "ip_camera_urls": "",
    "theme": "dark",
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


def parse_camera_indices(raw_value: str) -> list[int]:
    indices: list[int] = []
    for chunk in raw_value.replace("\n", ",").split(","):
        value = chunk.strip()
        if not value:
            continue
        try:
            index = int(value)
        except ValueError:
            continue
        if index not in indices:
            indices.append(index)
    return indices


def parse_ip_camera_urls(raw_value: str) -> list[str]:
    urls: list[str] = []
    for line in raw_value.splitlines():
        value = line.strip()
        if not value or value in urls:
            continue
        urls.append(value)
    return urls


def get_saved_camera_sources(settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    settings = settings or load_ui_settings()
    sources: list[dict[str, Any]] = []

    for index in parse_camera_indices(str(settings.get("camera_indices", ""))):
        sources.append(
            {
                "camera_id": index,
                "source": index,
                "label": f"CAM {index}",
                "kind": "local",
            }
        )

    for offset, url in enumerate(
        parse_ip_camera_urls(str(settings.get("ip_camera_urls", ""))), start=1
    ):
        sources.append(
            {
                "camera_id": 1000 + offset,
                "source": url,
                "label": f"IP Camera {offset}",
                "kind": "ip",
            }
        )

    return sources


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
        "paddle": importlib.util.find_spec("paddle") is not None,
        "safetensors": importlib.util.find_spec("safetensors") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "ultralytics": importlib.util.find_spec("ultralytics") is not None,
    }
    device = "CPU"
    yolo_device = "CPU"
    ocr_device = "CPU"
    torch_message = "torch not installed"
    if packages["torch"]:
        import torch

        try:
            if torch.cuda.is_available():
                yolo_device = f"CUDA ({torch.cuda.get_device_name(0)})"
            else:
                mps = getattr(torch.backends, "mps", None)
                if mps is not None and torch.backends.mps.is_available():
                    yolo_device = "MPS"
        except Exception:
            yolo_device = "CPU"
        torch_message = f"torch {torch.__version__}"
        if "+cpu" in torch.__version__:
            torch_message += " (CPU build)"

    paddle_message = "paddle not installed"
    if packages["paddle"]:
        try:
            _prepare_paddle_windows_runtime()
            import paddle

            try:
                if paddle.is_compiled_with_cuda():
                    ocr_device = "CUDA"
                else:
                    ocr_device = "CPU"
            except Exception:
                ocr_device = "CPU"
            paddle_message = f"paddle {paddle.__version__}"
            if ocr_device == "CPU":
                paddle_message += " (CPU build)"
        except Exception as exc:
            ocr_device = "GPU" if "gpu" in current_runtime_devices().get("ocr", "") else "CPU"
            try:
                paddle_message = (
                    f"paddle-gpu {importlib.metadata.version('paddlepaddle-gpu')}"
                )
            except importlib.metadata.PackageNotFoundError:
                paddle_message = "paddle installed"
            if ocr_device == "GPU":
                paddle_message += " (worker-mode GPU runtime)"
            else:
                paddle_message += f" (import issue: {type(exc).__name__})"

    try:
        runtime_devices = current_runtime_devices()
        device = f"YOLO: {runtime_devices['yolo']} | OCR: {runtime_devices['ocr']}"
    except Exception:
        device = f"YOLO: {yolo_device} | OCR: {ocr_device}"

    return {
        "model_path": str(model_path),
        "model_exists": "Yes" if model_path.exists() else "No",
        "ocr_cache": str(OCR_DIR),
        "device": device,
        "torch": torch_message,
        "opencv": "Installed" if packages["opencv"] else "Missing",
        "awiros_anpr": "Ready" if PADDLEOCR_SOURCE_DIR.exists() else "Missing Source",
        "paddle": paddle_message,
        "safetensors": "Installed" if packages["safetensors"] else "Missing",
        "ultralytics": "Installed" if packages["ultralytics"] else "Missing",
        "plate_log": str(PLATE_LOG_PATH),
        "watchlist": str(WATCHLIST_PATH),
        "outputs": str(OUTPUTS_DIR),
    }
