"""JWT-based authentication for the ANPR backend."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.storage.database import verify_user, get_user_by_id

_security = HTTPBearer(auto_error=False)


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


JWT_SECRET = _env("JWT_SECRET", "anpr-command-center-secret-key-change-in-production")
JWT_ALGORITHM = _env("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_MINUTES = int(_env("JWT_EXPIRY_MINUTES", "480"))


# ── Pydantic schemas ─────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserInfo(BaseModel):
    id: int
    username: str
    full_name: str
    role: str


# ── Token helpers ────────────────────────────────────────


def create_access_token(user_data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MINUTES)
    payload = {
        "sub": str(user_data["id"]),
        "username": user_data["username"],
        "role": user_data["role"],
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ── FastAPI dependencies ─────────────────────────────────


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    payload = decode_token(credentials.credentials)
    user_id = int(payload["sub"])
    return {
        "id": user_id,
        "username": payload.get("username", ""),
        "role": payload.get("role", ""),
    }


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# ── Login endpoint handler ───────────────────────────────


def authenticate(username: str, password: str) -> Optional[TokenResponse]:
    user = verify_user(username, password)
    if not user:
        return None
    token = create_access_token(user)
    return TokenResponse(access_token=token, user=user)
