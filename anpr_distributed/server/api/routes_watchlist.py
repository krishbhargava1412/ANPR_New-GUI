"""
Watchlist CRUD endpoints.

Replaces both watchlist.txt file operations and the SQLite Watchlist model.
Now includes threat_level and optional auto-expiry.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.rbac import get_current_user, require_role
from server.database.models import User, Watchlist
from server.database.session import get_async_session
from shared.schemas import WatchlistCreate, WatchlistResponse

LOGGER = logging.getLogger("anpr.server.api.watchlist")
router = APIRouter()


@router.get("/", response_model=list[WatchlistResponse])
async def list_watchlist(
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """List all watchlist entries."""
    result = await session.execute(
        select(Watchlist).order_by(Watchlist.added_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    body: WatchlistCreate,
    current_user: User = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_async_session),
):
    """Add a plate to the watchlist."""
    plate = body.plate_number.upper().strip()

    # Check for duplicate
    existing = await session.execute(
        select(Watchlist).where(Watchlist.plate_number == plate)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plate '{plate}' is already on the watchlist",
        )

    item = Watchlist(
        plate_number=plate,
        threat_level=body.threat_level,
        added_by=current_user.id,
        notes=body.notes,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)

    LOGGER.info("Plate '%s' added to watchlist by '%s'.", plate, current_user.username)
    return item


@router.delete("/{plate_number}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    plate_number: str,
    _current_user: User = Depends(require_role("operator")),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a plate from the watchlist."""
    result = await session.execute(
        select(Watchlist).where(Watchlist.plate_number == plate_number.upper())
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Plate not found in watchlist")

    await session.delete(item)
    await session.flush()
    LOGGER.info("Plate '%s' removed from watchlist.", plate_number.upper())


@router.get("/plates-only", response_model=list[str])
async def watchlist_plates_only(
    _current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get just the plate numbers (used by edge node for cache sync)."""
    result = await session.execute(select(Watchlist.plate_number))
    return [row[0] for row in result.all()]
