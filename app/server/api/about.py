"""About / system info API routes."""

from fastapi import APIRouter, Depends

from app.server.auth import get_current_user
from app.services.app_runtime import dependency_status

router = APIRouter(prefix="/api/about", tags=["about"])


@router.get("")
async def get_about(user: dict = Depends(get_current_user)):
    return dependency_status()
