"""Watchlist API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.server.auth import get_current_user
from app.services.app_runtime import watchlist_entries, save_watchlist_entries
from app.storage.database import add_watchlist_plate, remove_watchlist_plate

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    plate: str
    notes: str = ""


@router.get("")
async def get_watchlist(user: dict = Depends(get_current_user)):
    return {"plates": watchlist_entries()}


@router.post("")
async def add_plate(body: WatchlistAddRequest, user: dict = Depends(get_current_user)):
    success = add_watchlist_plate(body.plate, added_by=user["id"], notes=body.notes)
    return {"success": success, "plates": watchlist_entries()}


@router.delete("/{plate}")
async def remove_plate(plate: str, user: dict = Depends(get_current_user)):
    success = remove_watchlist_plate(plate)
    return {"success": success, "plates": watchlist_entries()}


@router.put("")
async def replace_watchlist(plates: list[str], user: dict = Depends(get_current_user)):
    save_watchlist_entries(plates)
    return {"plates": watchlist_entries()}
