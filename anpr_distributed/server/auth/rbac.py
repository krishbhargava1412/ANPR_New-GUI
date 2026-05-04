"""
Role-Based Access Control (RBAC) middleware and dependencies.

Roles hierarchy: admin > manager > operator > gate_keeper > viewer
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.jwt_handler import decode_token
from server.database.models import User
from server.database.session import get_async_session
from server.config import EDGE_API_KEY

LOGGER = logging.getLogger("anpr.server.auth.rbac")

# Role hierarchy — higher index = more privileges
ROLE_HIERARCHY = {
    "viewer": 0,
    "gate_keeper": 1,
    "operator": 2,
    "manager": 3,
    "admin": 4,
}

AVAILABLE_ROLES = list(ROLE_HIERARCHY.keys())


async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """
    FastAPI dependency: extract and validate the current user from the
    Authorization header (Bearer token).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — use an access token",
        )

    user_id = int(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return user


def require_role(minimum_role: str):
    """
    Returns a FastAPI dependency that checks if the current user has
    at least the specified role level.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
    """
    min_level = ROLE_HIERARCHY.get(minimum_role, 0)

    async def _check_role(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Requires at least '{minimum_role}' role.",
            )
        return current_user

    return _check_role


async def verify_edge_api_key(
    x_edge_api_key: Optional[str] = Header(None),
) -> str:
    """
    FastAPI dependency: verify the API key sent by edge nodes.
    Used for the /api/edge/* endpoints.
    """
    if not x_edge_api_key or x_edge_api_key != EDGE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing edge API key",
        )
    return x_edge_api_key
