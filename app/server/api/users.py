"""User management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.server.auth import get_current_user, require_admin
from app.storage.database import (
    create_user,
    delete_user,
    get_all_users,
    update_user_password,
    update_user_role,
    verify_user,
)

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "gate keeper"
    full_name: str = ""


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateRoleRequest(BaseModel):
    role: str


@router.get("")
async def list_users(user: dict = Depends(require_admin)):
    users = get_all_users()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name or u.username,
                "role": u.role,
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
                "is_active": u.is_active,
            }
            for u in users
        ]
    }


@router.post("")
async def create_new_user(body: CreateUserRequest, user: dict = Depends(require_admin)):
    new_user = create_user(
        body.username,
        body.password,
        body.role,
        created_by_admin_id=user["id"],
        full_name=body.full_name,
    )
    if not new_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"status": "created", "username": body.username}


@router.delete("/{user_id}")
async def remove_user(user_id: int, user: dict = Depends(require_admin)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    success = delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


@router.put("/{user_id}/role")
async def change_role(
    user_id: int, body: UpdateRoleRequest, user: dict = Depends(require_admin)
):
    success = update_user_role(user_id, body.role)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated"}


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    verified = verify_user(user["username"], body.current_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")
    success = update_user_password(user["id"], body.new_password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update password")
    return {"status": "password_changed"}
