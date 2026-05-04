"""
Edge node data ingestion endpoints.

These endpoints are called by the Jetson edge node to push detection data
and heartbeats to the server. Authenticated via API key (not JWT).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.rbac import verify_edge_api_key
from server.config import SNAPSHOTS_DIR
from server.database.models import Camera, Detection, Watchlist
from server.database.session import get_async_session
from shared.schemas import (
    DetectionBatchPayload,
    DetectionPayload,
    EdgeHeartbeat,
    WatchlistSyncResponse,
)

LOGGER = logging.getLogger("anpr.server.api.edge")
router = APIRouter()

# In-memory store for latest heartbeats per edge node
_edge_heartbeats: dict[str, dict] = {}


@router.post("/detections")
async def receive_detections(
    batch: DetectionBatchPayload,
    _api_key: str = Depends(verify_edge_api_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Receive a batch of detections from an edge node."""
    inserted = 0

    for det in batch.detections:
        # Resolve camera_id from edge camera identifier
        camera = await _resolve_camera(det.camera_id, session)
        if camera is None:
            LOGGER.warning("Unknown camera '%s', skipping detection.", det.camera_id)
            continue

        # Save snapshot if provided
        snapshot_path = None
        if det.snapshot_b64:
            snapshot_path = _save_snapshot(det, camera.id)

        detection = Detection(
            camera_id=camera.id,
            plate_number=det.plate_number,
            confidence=det.confidence,
            ocr_score=det.ocr_score,
            bbox=det.bbox,
            snapshot_path=snapshot_path,
            watchlist_hit=det.watchlist_hit,
            edge_node_id=det.edge_node_id,
            detected_at=det.detected_at,
        )
        session.add(detection)
        inserted += 1

    await session.flush()
    LOGGER.info(
        "Received %d detections from edge '%s' (%d inserted).",
        len(batch.detections), batch.edge_node_id, inserted,
    )
    return {"inserted": inserted, "skipped": len(batch.detections) - inserted}


@router.post("/heartbeat")
async def receive_heartbeat(
    heartbeat: EdgeHeartbeat,
    _api_key: str = Depends(verify_edge_api_key),
):
    """Receive health/status update from an edge node."""
    _edge_heartbeats[heartbeat.edge_node_id] = heartbeat.model_dump()
    LOGGER.debug(
        "Heartbeat from '%s': %d cameras, %.1f FPS, GPU %.1f°C",
        heartbeat.edge_node_id,
        heartbeat.active_cameras,
        heartbeat.inference_fps,
        heartbeat.gpu_temp_celsius or 0.0,
    )
    return {"status": "ok"}


@router.get("/heartbeats")
async def list_heartbeats(_api_key: str = Depends(verify_edge_api_key)):
    """Get latest heartbeats from all edge nodes."""
    return _edge_heartbeats


@router.get("/watchlist-sync", response_model=WatchlistSyncResponse)
async def sync_watchlist(
    _api_key: str = Depends(verify_edge_api_key),
    session: AsyncSession = Depends(get_async_session),
):
    """Provide the full watchlist for edge node to cache locally."""
    result = await session.execute(select(Watchlist.plate_number))
    plates = [row[0] for row in result.all()]
    return WatchlistSyncResponse(plates=plates, version=len(plates))


async def _resolve_camera(
    camera_identifier: str, session: AsyncSession
) -> Camera | None:
    """Resolve an edge camera ID string to a database Camera object."""
    # Try by name first
    result = await session.execute(
        select(Camera).where(Camera.name == camera_identifier)
    )
    camera = result.scalar_one_or_none()
    if camera:
        return camera

    # Try by numeric ID
    try:
        cam_id = int(camera_identifier.replace("cam_", ""))
        result = await session.execute(
            select(Camera).where(Camera.id == cam_id)
        )
        return result.scalar_one_or_none()
    except (ValueError, TypeError):
        return None


def _save_snapshot(det: DetectionPayload, camera_id: int) -> str | None:
    """Decode and save a base64-encoded snapshot JPEG."""
    try:
        jpeg_data = base64.b64decode(det.snapshot_b64)
        filename = (
            f"cam{camera_id}_{det.plate_number}_"
            f"{det.detected_at.strftime('%Y%m%d_%H%M%S')}.jpg"
        )
        path = SNAPSHOTS_DIR / filename
        path.write_bytes(jpeg_data)
        return str(path)
    except Exception as exc:
        LOGGER.warning("Failed to save snapshot: %s", exc)
        return None
