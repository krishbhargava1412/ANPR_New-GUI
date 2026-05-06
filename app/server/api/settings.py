"""Settings API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.server.auth import get_current_user
from app.services.app_runtime import available_model_names, load_ui_settings, save_ui_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(user: dict = Depends(get_current_user)):
    return load_ui_settings()


@router.put("")
async def update_settings(settings: dict, user: dict = Depends(get_current_user)):
    saved = save_ui_settings(settings)
    return saved


@router.get("/models")
async def get_models(user: dict = Depends(get_current_user)):
    return {"models": available_model_names()}
