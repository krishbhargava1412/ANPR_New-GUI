"""Dashboard API routes."""

from fastapi import APIRouter, Depends

from app.server.auth import get_current_user
from app.services.app_runtime import dashboard_stats, recent_detections, trend_snapshot

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    return dashboard_stats()


@router.get("/recent")
async def get_recent(limit: int = 12, user: dict = Depends(get_current_user)):
    return recent_detections(limit)


@router.get("/trend")
async def get_trend(user: dict = Depends(get_current_user)):
    return trend_snapshot()
