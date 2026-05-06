from __future__ import annotations

import logging
import os
from pathlib import Path

LOGGER = logging.getLogger("anpr_new_gui.storage")

APP_NAME = "ANPR_OCR"
APP_AUTHOR = "ANPR"


def get_database_url() -> str:
    """Return the PostgreSQL connection URL from environment or .env file."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Attempt to load from .env file at project root
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return "postgresql://anpr:anpr@localhost:5432/anpr"


# ---------------------------------------------------------------------------
# Model / OCR asset paths — these stay on the local filesystem because
# they are large binary files bundled with the repo.
# ---------------------------------------------------------------------------

APP_ROOT = Path(__file__).resolve().parents[2]


def get_awiros_anpr_dir() -> Path:
    return APP_ROOT / "assets" / "awiros_anpr"


def get_awiros_model_dir() -> Path:
    return get_awiros_anpr_dir() / "model"


def get_awiros_dict_path() -> Path:
    return get_awiros_anpr_dir() / "en_dict.txt"


def get_model_path(model_name: str) -> Path:
    return APP_ROOT / "assets" / "models" / model_name


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_storage() -> None:
    """Initialise storage by creating database tables."""
    from app.storage.database import init_db
    init_db()


def ensure_storage_dirs() -> None:
    """Legacy shim — no filesystem dirs needed with PostgreSQL.

    Ensures only the model directory exists since models are file-based.
    """
    models_dir = APP_ROOT / "assets" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
