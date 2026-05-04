"""
Detection history endpoints — paginated, filtered, exportable.

Replaces search_plate_log() CSV scanning with proper PostgreSQL queries.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.rbac import get_current_user, require_role
from server.database.models import Detection, User
from server.database.session import get_async_session
from shared.schemas import DetectionResponse

LOGGER = logging.getLogger("anpr.server.api.detections")
router = APIRouter()


@router.get("/", response_model=list[DetectionResponse])
async def list_detections(
    plate: Optional[str] = Query(None, description="Filter by plate number (partial match)"),
    camera_id: Optional[int] = Query(None, description="Filter by camera ID"),
    watchlist_only: bool = Query(False, description="Only show watchlist hits"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List detections with filtering and pagination."""
    query = select(Detection).order_by(Detection.detected_at.desc())

    if plate:
        query = query.where(Detection.plate_number.ilike(f"%{plate.upper()}%"))
    if camera_id is not None:
        query = query.where(Detection.camera_id == camera_id)
    if watchlist_only:
        query = query.where(Detection.watchlist_hit == True)
    if from_date:
        try:
            dt = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.where(Detection.detected_at >= dt)
        except ValueError:
            pass
    if to_date:
        try:
            dt = datetime.strptime(to_date, "%Y-%m-%d")
            query = query.where(Detection.detected_at <= dt.replace(hour=23, minute=59, second=59))
        except ValueError:
            pass

    query = query.offset(offset).limit(limit)
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def detection_stats(
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Aggregated statistics for the dashboard."""
    total = await session.execute(select(func.count(Detection.id)))
    unique = await session.execute(select(func.count(func.distinct(Detection.plate_number))))
    hits = await session.execute(
        select(func.count(Detection.id)).where(Detection.watchlist_hit == True)
    )
    avg_conf = await session.execute(select(func.avg(Detection.confidence)))

    return {
        "total_detections": total.scalar() or 0,
        "unique_plates": unique.scalar() or 0,
        "watchlist_hits": hits.scalar() or 0,
        "avg_confidence": round(avg_conf.scalar() or 0, 4),
    }


@router.get("/export")
async def export_detections(
    plate: Optional[str] = Query(None),
    watchlist_only: bool = Query(False),
    _current_user: User = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_async_session),
):
    """Export detections as CSV download."""
    query = select(Detection).order_by(Detection.detected_at.desc())

    if plate:
        query = query.where(Detection.plate_number.ilike(f"%{plate.upper()}%"))
    if watchlist_only:
        query = query.where(Detection.watchlist_hit == True)

    result = await session.execute(query)
    detections = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Plate", "Camera ID", "Confidence", "Watchlist Hit", "Snapshot"])

    for det in detections:
        writer.writerow([
            det.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
            det.plate_number,
            det.camera_id,
            f"{det.confidence:.4f}" if det.confidence else "",
            "Yes" if det.watchlist_hit else "No",
            det.snapshot_path or "",
        ])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=detections_export.csv"},
    )
