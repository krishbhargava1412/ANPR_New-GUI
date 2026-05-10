from __future__ import annotations

import importlib.metadata
import importlib.util
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage import get_awiros_anpr_dir, get_model_path
from app.storage.database import (
    add_detection_log,
    add_snapshot_blob,
    clear_all_snapshots,
    clear_detection_log,
    count_detection_log,
    delete_detection_entries,
    delete_snapshot,
    get_case_flags,
    get_settings,
    get_watchlist,
    get_watchlist_plates,
    search_detection_log,
    set_case_flag,
    set_settings,
)
from app.detection.legacy_backend import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    _prepare_paddle_windows_runtime,
    current_runtime_devices,
    loaded_model_path,
)

OCR_DIR = get_awiros_anpr_dir()
APP_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
    "frame_skip": 5,
    "save_snapshots": True,
    "watchlist_alerts_enabled": True,
    "sound_alerts_enabled": True,
    "proxy_resolution_enabled": True,
    "camera_indices": "",
    "default_camera": -1,
    "auto_start_cameras": False,
    "ip_camera_urls": "",
    "model_name": "LicensePlateDetector.pt",
    "theme": "dark",
}


# ── Settings (PostgreSQL-backed) ────────────────────────


def load_ui_settings() -> dict[str, Any]:
    stored = get_settings("ui")
    merged = DEFAULT_UI_SETTINGS.copy()
    if stored:
        merged.update(
            {k: v for k, v in stored.items() if k in DEFAULT_UI_SETTINGS}
        )
    return merged


def save_ui_settings(settings: dict[str, Any]) -> dict[str, Any]:
    model_name = settings.get("model_name")
    if model_name is not None:
        model_name = str(model_name).strip()
        available_models = set(available_model_names())
        settings = settings.copy()
        settings["model_name"] = (
            model_name
            if model_name in available_models
            else DEFAULT_UI_SETTINGS["model_name"]
        )

    merged = DEFAULT_UI_SETTINGS.copy()
    merged.update(settings)
    set_settings("ui", merged)
    return merged


def available_model_names() -> list[str]:
    model_dir = APP_ROOT / "assets" / "models"
    if not model_dir.exists():
        return ["LicensePlateDetector.pt"]
    names = sorted(
        [
            path.name
            for path in model_dir.iterdir()
            if path.is_file() and path.suffix in {".pt", ".onnx"}
        ]
    )
    return names or ["LicensePlateDetector.pt"]


# ── Camera Sources ──────────────────────────────────────


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


def get_saved_camera_sources(
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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


# ── Detection Log (PostgreSQL-backed) ───────────────────


def search_plate_log(
    plate: str = "",
    *,
    source_filter: str = "",
    watchlist_only: bool = False,
    from_date: str = "",
    to_date: str = "",
) -> list[dict[str, Any]]:
    from_dt = None
    to_dt = None
    try:
        if from_date:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        if to_date:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
    except ValueError:
        return []

    return search_detection_log(
        plate=plate.upper().strip() if plate else "",
        source_filter=source_filter.upper().strip() if source_filter else "",
        watchlist_only=watchlist_only,
        from_date=from_dt,
        to_date=to_dt,
    )


def recent_detections(limit: int = 12) -> list[dict[str, Any]]:
    entries = search_detection_log(limit=10000)
    if not entries:
        return []
    return list(reversed(entries[-max(1, limit):]))


def grouped_plate_history(
    matches: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entries = matches if matches is not None else search_plate_log()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(str(entry["plate"]), []).append(entry)

    flags = load_case_flags()
    groups: list[dict[str, Any]] = []
    for plate, plate_entries in grouped.items():
        confidences = [
            float(entry["confidence"])
            for entry in plate_entries
            if entry.get("confidence") is not None
        ]
        sorted_entries = sorted(
            plate_entries,
            key=lambda item: item.get("timestamp_dt") or datetime.min,
        )
        groups.append(
            {
                "plate": plate,
                "count": len(sorted_entries),
                "first_seen": sorted_entries[0]["timestamp"]
                if sorted_entries
                else "--",
                "last_seen": sorted_entries[-1]["timestamp"]
                if sorted_entries
                else "--",
                "avg_confidence": (
                    statistics.fmean(confidences) if confidences else None
                ),
                "watchlist_hit": any(
                    bool(item.get("watchlist_hit")) for item in sorted_entries
                ),
                "sources": sorted(
                    {str(item["source"]) for item in sorted_entries}
                ),
                "matches": sorted_entries,
                "flagged": bool(flags.get(plate, {}).get("flagged")),
                "note": str(flags.get(plate, {}).get("note", "")),
            }
        )

    groups.sort(
        key=lambda item: _safe_timestamp(item["last_seen"]),
        reverse=True,
    )
    return groups


def _safe_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.min


# ── Case Flags (PostgreSQL-backed) ──────────────────────


def load_case_flags() -> dict[str, dict[str, Any]]:
    return get_case_flags()


def save_case_flag(
    plate: str, flagged: bool, note: str = ""
) -> dict[str, dict[str, Any]]:
    set_case_flag(plate, flagged, note)
    return get_case_flags()


# ── Watchlist (PostgreSQL-backed) ───────────────────────


def watchlist_entries() -> list[str]:
    items = get_watchlist()
    return [item.plate_number for item in items]


def save_watchlist_entries(entries: list[str]) -> None:
    from app.storage.database import (
        add_watchlist_plate,
        get_watchlist_plates,
        remove_watchlist_plate,
    )

    current = get_watchlist_plates()
    desired = set()
    for entry in entries:
        plate = entry.strip().upper()
        if plate:
            desired.add(plate)

    # Remove plates no longer in list
    for plate in current - desired:
        remove_watchlist_plate(plate)

    # Add new plates
    for plate in desired - current:
        add_watchlist_plate(plate)


# ── Trend & Stats ───────────────────────────────────────


def trend_snapshot() -> dict[str, str]:
    detections = search_plate_log()
    now = datetime.now()
    windows = {
        "current": (now - timedelta(minutes=5), now),
        "previous": (now - timedelta(minutes=10), now - timedelta(minutes=5)),
    }

    def _count(start: datetime, end: datetime) -> int:
        return sum(
            1
            for entry in detections
            if entry.get("timestamp_dt") is not None
            and start <= entry["timestamp_dt"] <= end
        )

    current_hits = _count(*windows["current"])
    previous_hits = _count(*windows["previous"])
    delta = current_hits - previous_hits
    sign = "+" if delta >= 0 else ""
    spark_values = []
    for offset in range(5):
        end = now - timedelta(minutes=offset)
        start = end - timedelta(minutes=1)
        spark_values.append(_count(start, end))
    spark_values.reverse()
    return {
        "delta": f"{sign}{delta} plates/min",
        "direction": "up" if delta >= 0 else "down",
        "sparkline": " ".join(str(v) for v in spark_values),
        "current_rate": f"{current_hits / 5.0:.1f}",
    }


def clear_plate_log() -> None:
    clear_detection_log()


def delete_history_entries(entries_to_delete: list[dict[str, Any]]) -> int:
    entry_ids = [e["id"] for e in entries_to_delete if "id" in e]
    if entry_ids:
        return delete_detection_entries(entry_ids)
    return 0


def delete_snapshot_file(snapshot_id: Any) -> bool:
    if not snapshot_id:
        return False
    try:
        return delete_snapshot(int(snapshot_id))
    except (TypeError, ValueError):
        return False


def clear_outputs() -> int:
    return clear_all_snapshots()


# ── Dashboard Stats ─────────────────────────────────────


def dashboard_stats() -> dict[str, str]:
    detections = search_plate_log()
    unique_plates = len({entry["plate"] for entry in detections})
    watchlist_hits = sum(1 for entry in detections if entry["watchlist_hit"])
    confidence_values = [
        float(entry["confidence"])
        for entry in detections
        if entry.get("confidence") is not None
    ]
    latest = detections[-1]["timestamp"] if detections else "No detections yet"
    try:
        from app.server.main_server import get_detection_manager
        dm = get_detection_manager()
        active_cameras = len(dm._pipelines) if dm else 0
    except Exception:
        active_cameras = 0

    trend = trend_snapshot()
    return {
        "detections": str(len(detections)),
        "plates": str(unique_plates),
        "snapshots": "0",
        "watchlist_hits": str(watchlist_hits),
        "latest": latest,
        "active_cameras": str(active_cameras),
        "rate_per_min": trend["current_rate"],
        "avg_confidence": (
            f"{(sum(confidence_values) / len(confidence_values)) * 100:.0f}%"
            if confidence_values
            else "--"
        ),
        "trend_delta": trend["delta"],
        "trend_direction": trend["direction"],
        "sparkline": trend["sparkline"],
    }


# ── Dependency Status ───────────────────────────────────


def dependency_status() -> dict[str, str]:
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
                    current_device = paddle.device.get_device()
                    ocr_device = (
                        "CUDA"
                        if isinstance(current_device, str)
                        and current_device.lower().startswith("gpu")
                        else "CPU"
                    )
            except Exception:
                ocr_device = "CPU"
            paddle_message = f"paddle {paddle.__version__}"
            paddle_message += (
                " (CUDA build)" if ocr_device == "CUDA" else " (CPU build)"
            )
        except Exception as exc:
            ocr_device = (
                "GPU"
                if "gpu" in current_runtime_devices().get("ocr", "")
                else "CPU"
            )
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
        "awiros_anpr": "Ready (In-Repo Backend)",
        "paddle": paddle_message,
        "safetensors": "Installed" if packages["safetensors"] else "Missing",
        "ultralytics": "Installed" if packages["ultralytics"] else "Missing",
        "database": "PostgreSQL",
    }
