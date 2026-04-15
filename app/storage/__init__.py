from __future__ import annotations

import logging
import os
import shutil
import sys
import json
from pathlib import Path

from platformdirs import PlatformDirs

LOGGER = logging.getLogger("anpr_new_gui.storage")

APP_NAME = "ANPR_OCR"
APP_AUTHOR = "ANPR"

_platform_dirs = PlatformDirs(APP_NAME, APP_AUTHOR, ensure_exists=True)

USER_DATA_DIR = Path(_platform_dirs.user_data_dir)
USER_CONFIG_DIR = Path(_platform_dirs.user_config_dir)
USER_CACHE_DIR = Path(_platform_dirs.user_cache_dir)
USER_STATE_DIR = Path(_platform_dirs.user_state_dir)
STORAGE_CONFIG_PATH = USER_CONFIG_DIR / "storage_paths.json"


def _default_storage_paths() -> dict[str, str]:
    return {
        "snapshots_dir": str(USER_DATA_DIR / "snapshots"),
        "logs_dir": str(USER_DATA_DIR / "logs"),
        "videos_dir": str(USER_DATA_DIR / "logs" / "videos"),
        "watchlist_path": str(USER_DATA_DIR / "watchlist.txt"),
        "plate_log_path": str(USER_DATA_DIR / "logs" / "detected_plates_log.csv"),
        "settings_path": str(USER_DATA_DIR / "logs" / "ui_settings.json"),
        "db_path": str(USER_DATA_DIR / "anpr.db"),
        "models_dir": str(USER_DATA_DIR / "models"),
        "assets_dir": str(USER_DATA_DIR / "assets"),
    }


def load_storage_paths() -> dict[str, str]:
    defaults = _default_storage_paths()
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not STORAGE_CONFIG_PATH.exists():
        return defaults
    try:
        data = json.loads(STORAGE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    merged = defaults.copy()
    for key in defaults:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def save_storage_paths(paths: dict[str, str]) -> dict[str, str]:
    previous = load_storage_paths()
    current = previous.copy()
    for key, value in paths.items():
        if key in current and isinstance(value, str) and value.strip():
            current[key] = value.strip()
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_CONFIG_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    ensure_storage_dirs()
    for key in ("watchlist_path", "plate_log_path", "settings_path"):
        old_path = Path(previous[key])
        new_path = Path(current[key])
        if old_path == new_path or not old_path.exists() or new_path.exists():
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_path, new_path)
    return current


def get_app_dir() -> Path:
    return USER_DATA_DIR


def get_db_path() -> Path:
    return Path(load_storage_paths()["db_path"])


def get_snapshots_dir() -> Path:
    return Path(load_storage_paths()["snapshots_dir"])


def get_logs_dir() -> Path:
    return Path(load_storage_paths()["logs_dir"])


def get_watchlist_path() -> Path:
    return Path(load_storage_paths()["watchlist_path"])


def get_plate_log_path() -> Path:
    return Path(load_storage_paths()["plate_log_path"])


def get_ui_settings_path() -> Path:
    return Path(load_storage_paths()["settings_path"])


def get_assets_dir() -> Path:
    return Path(load_storage_paths()["assets_dir"])


def get_awiros_anpr_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "awiros_anpr"


def get_awiros_model_dir() -> Path:
    return get_awiros_anpr_dir() / "model"


def get_awiros_dict_path() -> Path:
    return get_awiros_anpr_dir() / "en_dict.txt"


def get_model_path(model_name: str) -> Path:
    return Path(load_storage_paths()["models_dir"]) / model_name


def ensure_storage_dirs() -> None:
    configured = load_storage_paths()
    dirs = [
        USER_DATA_DIR,
        USER_CONFIG_DIR,
        USER_CACHE_DIR,
        USER_STATE_DIR,
        get_snapshots_dir(),
        get_logs_dir(),
        get_assets_dir(),
        Path(configured["models_dir"]),
        Path(configured["videos_dir"]),
        get_db_path().parent,
        get_watchlist_path().parent,
        get_plate_log_path().parent,
        get_ui_settings_path().parent,
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)

    watchlist = get_watchlist_path()
    if not watchlist.exists():
        watchlist.write_text("", encoding="utf-8")


def migrate_from_legacy(source_root: Path) -> None:
    if not source_root.exists():
        return

    legacy_outputs = source_root / "outputs"
    if legacy_outputs.exists():
        LOGGER.info("Migrating legacy data from %s", legacy_outputs)

        legacy_snapshots = legacy_outputs / "snapshots"
        if legacy_snapshots.exists():
            dest_snapshots = get_snapshots_dir()
            for item in legacy_snapshots.iterdir():
                try:
                    shutil.copy2(item, dest_snapshots / item.name)
                except Exception as e:
                    LOGGER.warning("Failed to copy snapshot %s: %s", item.name, e)

        legacy_logs = legacy_outputs / "logs"
        if legacy_logs.exists():
            dest_logs = get_logs_dir()
            for item in legacy_logs.iterdir():
                if item.is_file():
                    try:
                        shutil.copy2(item, dest_logs / item.name)
                    except Exception as e:
                        LOGGER.warning("Failed to copy log %s: %s", item.name, e)

        legacy_watchlist = legacy_outputs / "watchlist.txt"
        if legacy_watchlist.exists():
            dest_watchlist = get_watchlist_path()
            if not dest_watchlist.exists() or dest_watchlist.stat().st_size == 0:
                shutil.copy2(legacy_watchlist, dest_watchlist)

        legacy_assets = source_root / "assets"
        if legacy_assets.exists():
            dest_assets = get_assets_dir()

            legacy_models = legacy_assets / "models"
            if legacy_models.exists():
                dest_models = USER_DATA_DIR / "models"
                for item in legacy_models.iterdir():
                    if item.is_file():
                        dest_item = dest_models / item.name
                        if not dest_item.exists():
                            try:
                                shutil.copy2(item, dest_item)
                            except Exception as e:
                                LOGGER.warning("Failed to copy model %s: %s", item.name, e)

        LOGGER.info("Legacy data migration complete")


def init_storage() -> None:
    ensure_storage_dirs()
    app_dir = Path(__file__).resolve().parents[1].parent
    legacy_path = app_dir.parent / "assets"
    if legacy_path.exists():
        migrate_from_legacy(app_dir.parent)
