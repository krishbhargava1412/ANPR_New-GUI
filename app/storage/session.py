from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.storage.database import User, verify_user

_current_user: Optional[User] = None


@dataclass
class Session:
    user: User
    is_authenticated: bool = True


def login(username: str, password: str) -> Optional[Session]:
    global _current_user
    user = verify_user(username, password)
    if user:
        _current_user = user
        return Session(user=user)
    return None


def logout() -> None:
    global _current_user
    _current_user = None


def get_current_user() -> Optional[User]:
    return _current_user


def get_current_session() -> Optional[Session]:
    if _current_user is None:
        return None
    return Session(user=_current_user)


def is_admin() -> bool:
    return _current_user is not None and _current_user.role == "admin"


def is_authenticated() -> bool:
    return _current_user is not None


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