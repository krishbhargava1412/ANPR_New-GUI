"""Camera management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.server.auth import get_current_user
from app.services.app_runtime import get_saved_camera_sources, load_ui_settings

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("")
async def list_cameras(user: dict = Depends(get_current_user)):
    """List all configured camera sources."""
    sources = get_saved_camera_sources()
    try:
        from app.server.main_server import get_detection_manager
        dm = get_detection_manager()
        if dm:
            for src in sources:
                cid = src["camera_id"]
                src["status"] = dm.get_camera_status(cid)
                src["running"] = dm.is_camera_running(cid)
        else:
            for src in sources:
                src["status"] = "Idle"
                src["running"] = False
    except Exception:
        for src in sources:
            src["status"] = "Idle"
            src["running"] = False
    return {"cameras": sources}


@router.post("/scan")
async def scan_local_cameras(user: dict = Depends(get_current_user)):
    """Probe local camera indices 0-4."""
    import cv2
    available = []
    for idx in range(5):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            available.append(idx)
            cap.release()
    return {"available": available}
