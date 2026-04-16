from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage import (
    get_snapshots_dir,
    get_logs_dir,
    get_watchlist_path,
    get_plate_log_path,
    get_ui_settings_path,
    ensure_storage_dirs,
    get_db_path,
    get_awiros_anpr_dir,
    load_storage_paths,
    save_storage_paths,
)

from app.detection.legacy_backend import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PADDLEOCR_SOURCE_DIR,
    _prepare_paddle_windows_runtime,
    current_runtime_devices,
    ensure_runtime_dirs,
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


def get_outputs_dir() -> Path:
    return get_snapshots_dir()


def get_output_log_dir() -> Path:
    return get_logs_dir()


def get_snapshot_dir() -> Path:
    return get_snapshots_dir()


def get_watchlist_runtime_path() -> Path:
    return get_watchlist_path()


def get_plate_log_runtime_path() -> Path:
    return get_plate_log_path()


def get_output_csv_dir() -> Path:
    return get_logs_dir() / "csv"


def get_output_video_dir() -> Path:
    return Path(load_storage_paths()["videos_dir"])


def get_settings_path() -> Path:
    return get_ui_settings_path()


def get_app_log_path() -> Path:
    return get_logs_dir() / "anpr_app.log"


def get_case_flags_path() -> Path:
    return get_logs_dir() / "case_flags.json"


def ensure_app_dirs() -> None:
    ensure_storage_dirs()
    get_output_csv_dir().mkdir(parents=True, exist_ok=True)
    get_output_video_dir().mkdir(parents=True, exist_ok=True)


def load_ui_settings() -> dict[str, Any]:
    ensure_app_dirs()
    settings_path = get_settings_path()
    if not settings_path.exists():
        return DEFAULT_UI_SETTINGS.copy()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
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
    get_settings_path().write_text(json.dumps(merged, indent=2), encoding="utf-8")
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
    plate_log_path = get_plate_log_runtime_path()
    if not plate_log_path.exists():
        return matches
    plate = plate.upper().strip()
    source_filter = source_filter.upper().strip()
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d") if from_date else None
        to_dt = datetime.strptime(to_date, "%Y-%m-%d") if to_date else None
    except ValueError:
        return matches
    with open(plate_log_path, newline="", encoding="utf-8") as file:
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


def recent_detections(limit: int = 12) -> list[dict[str, Any]]:
    entries = search_plate_log()
    if not entries:
        return []
    return list(reversed(entries[-max(1, limit) :]))


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
                "first_seen": sorted_entries[0]["timestamp"] if sorted_entries else "--",
                "last_seen": sorted_entries[-1]["timestamp"] if sorted_entries else "--",
                "avg_confidence": (
                    statistics.fmean(confidences) if confidences else None
                ),
                "watchlist_hit": any(
                    bool(item.get("watchlist_hit")) for item in sorted_entries
                ),
                "sources": sorted({str(item["source"]) for item in sorted_entries}),
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


def load_case_flags() -> dict[str, dict[str, Any]]:
    ensure_app_dirs()
    case_flags_path = get_case_flags_path()
    if not case_flags_path.exists():
        return {}
    try:
        data = json.loads(case_flags_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_case_flag(plate: str, flagged: bool, note: str = "") -> dict[str, dict[str, Any]]:
    data = load_case_flags()
    cleaned_plate = plate.upper().strip()
    if not cleaned_plate:
        return data
    data[cleaned_plate] = {
        "flagged": bool(flagged),
        "note": note.strip(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    get_case_flags_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def watchlist_entries() -> list[str]:
    watchlist_path = get_watchlist_runtime_path()
    if not watchlist_path.exists():
        return []
    return [
        line.strip().upper()
        for line in watchlist_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save_watchlist_entries(entries: list[str]) -> None:
    watchlist_path = get_watchlist_runtime_path()
    watchlist_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = []
    for entry in entries:
        plate = entry.strip().upper()
        if plate and plate not in cleaned:
            cleaned.append(plate)
    watchlist_path.write_text("\n".join(cleaned), encoding="utf-8")


def trend_snapshot() -> dict[str, str]:
    detections = search_plate_log()
    now = datetime.now()
    windows = {
        "current": (
            now - timedelta(minutes=5),
            now,
        ),
        "previous": (
            now - timedelta(minutes=10),
            now - timedelta(minutes=5),
        ),
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
    direction = "up" if delta >= 0 else "down"
    sign = "+" if delta >= 0 else ""
    spark_values = []
    for offset in range(5):
        end = now - timedelta(minutes=offset)
        start = end - timedelta(minutes=1)
        spark_values.append(_count(start, end))
    spark_values.reverse()
    return {
        "delta": f"{sign}{delta} plates/min",
        "direction": direction,
        "sparkline": " ".join(str(value) for value in spark_values),
        "current_rate": f"{current_hits / 5.0:.1f}",
    }


def clear_plate_log() -> None:
    plate_log_path = get_plate_log_runtime_path()
    if plate_log_path.exists():
        plate_log_path.unlink()


def delete_history_entries(entries_to_delete: list[dict[str, Any]]) -> int:
    plate_log_path = get_plate_log_runtime_path()
    if not plate_log_path.exists():
        return 0
    delete_keys = {
        (
            str(entry.get("timestamp", "")),
            str(entry.get("plate", "")),
            str(entry.get("source", "")),
            "" if entry.get("confidence") is None else f"{float(entry['confidence']):.4f}",
            str(entry.get("snapshot_path", "")),
            "1" if entry.get("watchlist_hit") else "0",
        )
        for entry in entries_to_delete
    }
    kept_rows: list[list[str]] = []
    deleted = 0
    with open(plate_log_path, newline="", encoding="utf-8") as file:
        for row in csv.reader(file):
            entry = parse_plate_log_row(row)
            if not entry:
                kept_rows.append(row)
                continue
            row_key = (
                entry["timestamp"],
                entry["plate"],
                entry["source"],
                "" if entry["confidence"] is None else f"{float(entry['confidence']):.4f}",
                str(entry.get("snapshot_path", "")),
                "1" if entry.get("watchlist_hit") else "0",
            )
            if row_key in delete_keys:
                deleted += 1
                continue
            kept_rows.append(row)
    with open(plate_log_path, "w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(kept_rows)
    return deleted


def delete_snapshot_file(snapshot_path: str | Path | None) -> bool:
    if not snapshot_path:
        return False
    path = Path(snapshot_path)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def clear_outputs() -> int:
    count = 0
    snapshot_dir = get_snapshot_dir()
    if snapshot_dir.exists():
        for f in snapshot_dir.glob("*.png"):
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
    confidence_values = [
        float(entry["confidence"])
        for entry in detections
        if entry.get("confidence") is not None
    ]
    snapshot_count = (
        len(list(get_snapshot_dir().glob("*.png"))) if get_snapshot_dir().exists() else 0
    )
    latest = detections[-1]["timestamp"] if detections else "No detections yet"
    recent_cutoff = datetime.now() - timedelta(minutes=5)
    recent_hits = [
        entry
        for entry in detections
        if entry["timestamp_dt"] is not None and entry["timestamp_dt"] >= recent_cutoff
    ]
    configured_cameras = len(get_saved_camera_sources())
    trend = trend_snapshot()
    return {
        "detections": str(len(detections)),
        "plates": str(unique_plates),
        "snapshots": str(snapshot_count),
        "watchlist_hits": str(watchlist_hits),
        "latest": latest,
        "active_cameras": str(configured_cameras),
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
        "plate_log": str(get_plate_log_runtime_path()),
        "watchlist": str(get_watchlist_runtime_path()),
        "outputs": str(get_outputs_dir()),
    }
