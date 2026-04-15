from __future__ import annotations

import logging
import os
import shutil
import sys
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


def get_app_dir() -> Path:
    return USER_DATA_DIR


def get_db_path() -> Path:
    return USER_DATA_DIR / "anpr.db"


def get_snapshots_dir() -> Path:
    return USER_DATA_DIR / "snapshots"


def get_logs_dir() -> Path:
    return USER_DATA_DIR / "logs"


def get_watchlist_path() -> Path:
    return USER_DATA_DIR / "watchlist.txt"


def get_plate_log_path() -> Path:
    return get_logs_dir() / "detected_plates_log.csv"


def get_assets_dir() -> Path:
    return USER_DATA_DIR / "assets"


def get_awiros_anpr_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets" / "awiros_anpr"


def get_awiros_model_dir() -> Path:
    return get_awiros_anpr_dir() / "model"


def get_awiros_dict_path() -> Path:
    return get_awiros_anpr_dir() / "en_dict.txt"


def get_model_path(model_name: str) -> Path:
    return USER_DATA_DIR / "models" / model_name


def ensure_storage_dirs() -> None:
    dirs = [
        USER_DATA_DIR,
        USER_CONFIG_DIR,
        USER_CACHE_DIR,
        USER_STATE_DIR,
        get_snapshots_dir(),
        get_logs_dir(),
        get_assets_dir(),
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
