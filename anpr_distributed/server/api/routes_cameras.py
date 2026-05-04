"""
Camera management endpoints.

Cameras are now first-class database entities instead of JSON strings
in ui_settings.json.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.rbac import get_current_user, require_role
from server.database.models import Camera, User
from server.database.session import get_async_session
from shared.schemas import CameraCreate, CameraResponse

LOGGER = logging.getLogger("anpr.server.api.cameras")
router = APIRouter()


@router.get("/", response_model=list[CameraResponse])
async def list_cameras(
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all configured cameras."""
    result = await session.execute(
        select(Camera).order_by(Camera.id)
    )
    return result.scalars().all()


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def add_camera(
    body: CameraCreate,
    current_user: User = Depends(require_role("manager")),
    session: AsyncSession = Depends(get_async_session),
):
    """Add a new camera source."""
    camera = Camera(
        name=body.name,
        source_url=body.source_url,
        source_type=body.source_type,
        location=body.location,
        added_by=current_user.id,
    )
    session.add(camera)
    await session.flush()
    await session.refresh(camera)
    LOGGER.info("Camera '%s' added by user '%s'.", body.name, current_user.username)
    return camera


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: int,
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get a specific camera by ID."""
    result = await session.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: int,
    body: CameraCreate,
    _current_user: User = Depends(require_role("manager")),
    session: AsyncSession = Depends(get_async_session),
):
    """Update a camera configuration."""
    result = await session.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    camera.name = body.name
    camera.source_url = body.source_url
    camera.source_type = body.source_type
    camera.location = body.location
    await session.flush()
    await session.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: int,
    _current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a camera (admin only)."""
    result = await session.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    await session.delete(camera)
    await session.flush()
    LOGGER.info("Camera '%s' (id=%d) deleted.", camera.name, camera_id)
