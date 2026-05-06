"""Detection control API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.server.auth import get_current_user

router = APIRouter(prefix="/api/detection", tags=["detection"])


@router.get("/status")
async def get_status(user: dict = Depends(get_current_user)):
    try:
        from app.server.main_server import get_detection_manager
        dm = get_detection_manager()
        if dm:
            return dm.status()
        return {"running": False, "paused": False, "cameras": {}}
    except Exception:
        return {"running": False, "paused": False, "cameras": {}}


@router.post("/start")
async def start_detection(user: dict = Depends(get_current_user)):
    from app.server.main_server import get_detection_manager
    dm = get_detection_manager()
    if dm:
        dm.start_all()
    return {"status": "started"}


@router.post("/stop")
async def stop_detection(user: dict = Depends(get_current_user)):
    from app.server.main_server import get_detection_manager
    dm = get_detection_manager()
    if dm:
        dm.stop_all()
    return {"status": "stopped"}


@router.post("/pause")
async def pause_detection(user: dict = Depends(get_current_user)):
    from app.server.main_server import get_detection_manager
    dm = get_detection_manager()
    if dm:
        dm.toggle_pause()
    return {"status": "toggled"}
