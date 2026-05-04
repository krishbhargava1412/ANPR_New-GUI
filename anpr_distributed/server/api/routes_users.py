"""
User management endpoints (admin only).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.password import hash_password
from server.auth.rbac import require_role
from server.database.models import User
from server.database.session import get_async_session
from shared.schemas import UserCreate, UserResponse, UserUpdate

LOGGER = logging.getLogger("anpr.server.api.users")
router = APIRouter()


@router.get("/", response_model=list[UserResponse])
async def list_users(
    _current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_async_session),
):
    existing = await session.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Username '{body.username}' already exists")

    user = User(
        username=body.username,
        full_name=body.full_name or body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        created_by=current_user.id,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int, body: UserUpdate,
    _: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        if user.username == "admin" and not body.is_active:
            raise HTTPException(400, "Cannot deactivate admin")
        user.is_active = body.is_active
    await session.flush()
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    _: User = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if user.username == "admin":
        raise HTTPException(400, "Cannot delete default admin")
    await session.delete(user)
    await session.flush()
