"""
Dashboard stats endpoint. Replaces dashboard_stats() CSV scanning.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.rbac import get_current_user
from server.database.models import Camera, Detection, User
from server.database.session import get_async_session
from shared.schemas import DashboardStats

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    now = datetime.now(timezone.utc)
    five_min_ago = now - timedelta(minutes=5)

    total = (await session.execute(select(func.count(Detection.id)))).scalar() or 0
    unique = (await session.execute(
        select(func.count(func.distinct(Detection.plate_number)))
    )).scalar() or 0
    hits = (await session.execute(
        select(func.count(Detection.id)).where(Detection.watchlist_hit == True)
    )).scalar() or 0
    active_cams = (await session.execute(
        select(func.count(Camera.id)).where(Camera.is_active == True)
    )).scalar() or 0
    avg_conf = (await session.execute(select(func.avg(Detection.confidence)))).scalar()
    recent = (await session.execute(
        select(func.count(Detection.id)).where(Detection.detected_at >= five_min_ago)
    )).scalar() or 0

    return DashboardStats(
        total_detections=total,
        unique_plates=unique,
        watchlist_hits=hits,
        active_cameras=active_cams,
        recent_rate_per_min=round(recent / 5.0, 1),
        avg_confidence=round(avg_conf, 4) if avg_conf else None,
    )
