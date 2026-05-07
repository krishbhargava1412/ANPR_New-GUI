"""FastAPI application factory for the ANPR Command Center backend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.server.auth import LoginRequest, authenticate
from app.server.api import dashboard, history, watchlist, settings, cameras, detection, users, about, snapshots
from app.server.ws import feed_handler
from app.storage import init_storage

LOGGER = logging.getLogger("anpr_new_gui.server")

_detection_manager = None


def get_detection_manager():
    return _detection_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _detection_manager

    LOGGER.info("Initialising storage...")
    init_storage()

    import asyncio
    from app.detection.detection_manager import DetectionManager
    _detection_manager = DetectionManager()
    _detection_manager.set_event_loop(asyncio.get_running_loop())
    LOGGER.info("ANPR backend ready — waiting for client camera frames")

    yield

    LOGGER.info("Shutting down...")
    if _detection_manager:
        _detection_manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ANPR Command Center",
        version="2.0.0",
        description="Distributed ANPR backend with real-time detection",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Auth endpoints ─────────────────────────────────
    from app.server.auth import get_current_user
    from fastapi import Depends, HTTPException

    @app.post("/api/auth/login")
    async def login(body: LoginRequest):
        result = authenticate(body.username, body.password)
        if not result:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return result

    @app.get("/api/auth/me")
    async def me(user: dict = Depends(get_current_user)):
        return user

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "2.0.0"}

    # ── API routers ────────────────────────────────────
    app.include_router(dashboard.router)
    app.include_router(history.router)
    app.include_router(watchlist.router)
    app.include_router(settings.router)
    app.include_router(cameras.router)
    app.include_router(detection.router)
    app.include_router(users.router)
    app.include_router(about.router)
    app.include_router(snapshots.router)

    # ── WebSocket ──────────────────────────────────────
    app.include_router(feed_handler.router)

    # ── Static Files (Frontend) ────────────────────────
    # We mount this last so it doesn't catch API routes.
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/css", StaticFiles(directory=str(web_dir / "css")), name="css")
        app.mount("/js", StaticFiles(directory=str(web_dir / "js")), name="js")
        app.mount("/assets", StaticFiles(directory=str(Path(__file__).resolve().parent.parent.parent / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # If the path looks like a file (has an extension), but wasn't caught by the mounts, 
            # it's probably a missing static asset.
            if "." in full_path.split("/")[-1]:
                return FileResponse(str(web_dir / "index.html")) # Or 404
            
            # For SPA, return index.html for any other route
            return FileResponse(str(web_dir / "index.html"))

    return app

app = create_app()
