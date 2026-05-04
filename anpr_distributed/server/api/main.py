"""
FastAPI application factory.

Wires together all route modules, CORS, lifespan events, static file serving,
and middleware. The web dashboard is served as static files from /frontend/.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import CORS_ORIGINS, LOG_LEVEL
from server.database.migrations import init_database

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger("anpr.server.api")

# Resolve the frontend directory (relative to the project root)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    LOGGER.info("Starting ANPR Server — initializing database...")
    await init_database()
    LOGGER.info("Database ready. Server accepting requests.")
    if FRONTEND_DIR.exists():
        LOGGER.info("Web dashboard available at http://0.0.0.0:8000/")
    else:
        LOGGER.warning("Frontend directory not found at %s — dashboard will not be served.", FRONTEND_DIR)
    yield
    LOGGER.info("ANPR Server shutting down.")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="ANPR Command Center — DRDO Server",
        description=(
            "Backend API for the Automatic Number Plate Recognition system. "
            "Receives detections from Jetson edge nodes and serves data to "
            "multi-user web dashboards."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    # CORS — allow the web dashboard origin(s)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Register API route modules ────────────────────────────────────────
    from server.api.routes_auth import router as auth_router
    from server.api.routes_detections import router as detections_router
    from server.api.routes_cameras import router as cameras_router
    from server.api.routes_watchlist import router as watchlist_router
    from server.api.routes_users import router as users_router
    from server.api.routes_dashboard import router as dashboard_router
    from server.api.routes_edge import router as edge_router

    app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
    app.include_router(detections_router, prefix="/api/detections", tags=["Detections"])
    app.include_router(cameras_router, prefix="/api/cameras", tags=["Cameras"])
    app.include_router(watchlist_router, prefix="/api/watchlist", tags=["Watchlist"])
    app.include_router(users_router, prefix="/api/users", tags=["User Management"])
    app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
    app.include_router(edge_router, prefix="/api/edge", tags=["Edge Nodes"])

    @app.get("/api/health", tags=["Health"])
    async def health_check():
        return {"status": "ok", "service": "anpr-server"}

    # ── Serve Web Dashboard (static files) ────────────────────────────────
    if FRONTEND_DIR.exists():
        static_dir = FRONTEND_DIR / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        index_html = FRONTEND_DIR / "index.html"

        @app.get("/", include_in_schema=False)
        async def serve_root():
            return FileResponse(str(index_html))

        # Catch-all for SPA client-side routing (non-API paths)
        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str):
            # If it's a real file in static/, let StaticFiles handle it
            file_path = FRONTEND_DIR / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for SPA routing
            return FileResponse(str(index_html))

    return app
