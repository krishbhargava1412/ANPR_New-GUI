"""History API routes."""

from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.server.auth import get_current_user
from app.services.app_runtime import (
    clear_plate_log,
    delete_history_entries,
    delete_snapshot_file,
    grouped_plate_history,
    load_case_flags,
    save_case_flag,
    search_plate_log,
)

router = APIRouter(prefix="/api/history", tags=["history"])


class FlagRequest(BaseModel):
    plate: str
    flagged: bool
    note: str = ""


class DeleteRequest(BaseModel):
    entry_ids: list[int]


@router.get("")
async def get_history(
    plate: str = "",
    source: str = "",
    watchlist_only: bool = False,
    from_date: str = "",
    to_date: str = "",
    user: dict = Depends(get_current_user),
):
    matches = search_plate_log(
        plate,
        source_filter=source,
        watchlist_only=watchlist_only,
        from_date=from_date,
        to_date=to_date,
    )
    groups = grouped_plate_history(matches)
    return {"matches": matches, "groups": groups}


@router.post("/export")
async def export_csv(
    plate: str = "",
    source: str = "",
    user: dict = Depends(get_current_user),
):
    matches = search_plate_log(plate, source_filter=source)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Time", "Plate", "Source", "Confidence", "Watchlist"])
    for m in matches:
        writer.writerow([
            m.get("timestamp", ""),
            m.get("plate", ""),
            m.get("source", ""),
            m.get("confidence", ""),
            "Yes" if m.get("watchlist_hit") else "No",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=history_export.csv"},
    )


@router.post("/clear")
async def clear_history(user: dict = Depends(get_current_user)):
    clear_plate_log()
    return {"status": "ok"}


@router.post("/delete")
async def delete_entries(body: DeleteRequest, user: dict = Depends(get_current_user)):
    deleted = delete_history_entries([{"id": eid} for eid in body.entry_ids])
    return {"deleted": deleted}


@router.post("/flag")
async def flag_plate(body: FlagRequest, user: dict = Depends(get_current_user)):
    flags = save_case_flag(body.plate, body.flagged, body.note)
    return {"flags": flags}


@router.get("/flags")
async def get_flags(user: dict = Depends(get_current_user)):
    return load_case_flags()
