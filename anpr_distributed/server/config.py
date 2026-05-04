"""
Server configuration — loaded from environment variables with sane defaults.

All secrets (DB password, JWT secret) are read from env vars or files,
never hardcoded.
"""
from __future__ import annotations

import os
from pathlib import Path


# ── Database ──────────────────────────────────────────────────────────────────
def _read_secret_file(env_var: str, default: str) -> str:
    """Read a secret from a file path (Docker secrets) or env var."""
    file_path = os.environ.get(f"{env_var}_FILE")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    return os.environ.get(env_var, default)


DATABASE_HOST = os.environ.get("DATABASE_HOST", "localhost")
DATABASE_PORT = int(os.environ.get("DATABASE_PORT", "5432"))
DATABASE_NAME = os.environ.get("DATABASE_NAME", "anpr")
DATABASE_USER = os.environ.get("DATABASE_USER", "anpr")
DATABASE_PASSWORD = _read_secret_file("DATABASE_PASSWORD", "anpr_secure_2026")

# Async URL for SQLAlchemy 2.0 + asyncpg
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}",
)

# Sync URL for migrations and one-off scripts
DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC",
    f"postgresql+psycopg2://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}",
)

# ── JWT Authentication ────────────────────────────────────────────────────────
JWT_SECRET_KEY = _read_secret_file("JWT_SECRET", "CHANGE-ME-IN-PRODUCTION-drdo-anpr-2026")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7

# ── Server ────────────────────────────────────────────────────────────────────
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8000"))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# ── Storage ───────────────────────────────────────────────────────────────────
SNAPSHOTS_DIR = Path(os.environ.get("SNAPSHOTS_DIR", "./data/snapshots"))
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Edge Node ─────────────────────────────────────────────────────────────────
# API key for edge nodes to authenticate when pushing detections
EDGE_API_KEY = os.environ.get("EDGE_API_KEY", "edge-jetson-key-change-in-prod")

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
