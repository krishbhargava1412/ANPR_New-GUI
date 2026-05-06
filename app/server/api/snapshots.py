"""Snapshot serving API routes — serves images from PostgreSQL BYTEA."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.server.auth import get_current_user
from app.storage.database import get_snapshot_image

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("/{snapshot_id}")
async def get_snapshot(snapshot_id: int, user: dict = Depends(get_current_user)):
    result = get_snapshot_image(snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    image_data, content_type = result
    return Response(content=image_data, media_type=content_type)
