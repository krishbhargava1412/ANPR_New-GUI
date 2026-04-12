from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.storage.database import verify_user

_current_user: Optional[dict] = None


@dataclass
class Session:
    user_id: int
    username: str
    role: str
    admin_id: Optional[int] = None
    is_authenticated: bool = True


def login(username: str, password: str) -> Optional[Session]:
    global _current_user
    user = verify_user(username, password)
    if user:
        _current_user = user
        admin_id = user["id"] if user["role"] == "admin" else user.get("created_by_admin_id")
        return Session(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            admin_id=admin_id,
        )
    return None


def logout() -> None:
    global _current_user
    _current_user = None


def get_current_user() -> Optional[dict]:
    return _current_user


def get_current_session() -> Optional[Session]:
    if _current_user is None:
        return None
    admin_id = _current_user["id"] if _current_user["role"] == "admin" else _current_user.get("created_by_admin_id")
    return Session(
        user_id=_current_user["id"],
        username=_current_user["username"],
        role=_current_user["role"],
        admin_id=admin_id,
    )


def is_admin() -> bool:
    return _current_user is not None and _current_user.get("role") == "admin"


def is_authenticated() -> bool:
    return _current_user is not None


def get_current_user_id() -> Optional[int]:
    return _current_user.get("id") if _current_user else None


def require_auth(func):
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            raise PermissionError("Authentication required")
        return func(*args, **kwargs)
    return wrapper


def require_admin(func):
    def wrapper(*args, **kwargs):
        if not is_admin():
            raise PermissionError("Admin access required")
        return func(*args, **kwargs)
    return wrapper