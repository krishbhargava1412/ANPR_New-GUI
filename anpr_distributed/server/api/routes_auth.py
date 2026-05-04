"""
Authentication endpoints: login, token refresh, change password.

Replaces the in-memory session.py login/logout with JWT-based stateless auth.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.jwt_handler import create_access_token, create_refresh_token, decode_token
from server.auth.password import hash_password, verify_password, needs_rehash
from server.auth.rbac import get_current_user
from server.database.models import User
from server.database.session import get_async_session
from shared.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    TokenRefreshRequest,
)

LOGGER = logging.getLogger("anpr.server.api.auth")
router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Authenticate user and return JWT token pair."""
    result = await session.execute(
        select(User).where(User.username == body.username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Rehash if parameters changed (transparent upgrade)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    user.last_login = datetime.now(timezone.utc)
    await session.flush()

    access_token = create_access_token(user.id, user.username, user.role, user.full_name)
    refresh_token = create_refresh_token(user.id)

    LOGGER.info("User '%s' logged in successfully.", user.username)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = int(payload["sub"])
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    access_token = create_access_token(user.id, user.username, user.role, user.full_name)
    refresh_token_new = create_refresh_token(user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_new,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Change the current user's password."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    result = await session.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    user.password_hash = hash_password(body.new_password)
    await session.flush()

    LOGGER.info("User '%s' changed their password.", current_user.username)
    return {"message": "Password changed successfully"}
