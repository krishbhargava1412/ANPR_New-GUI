from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.storage import get_db_path, ensure_storage_dirs

LOGGER = logging.getLogger("anpr_new_gui.storage.database")
AVAILABLE_USER_ROLES = [
    "gate keeper",
    "manager",
    "operator",
    "viewer",
    "admin",
]


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    detection_history: Mapped[list["DetectionHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        ).hex()

    def verify_password(self, password: str) -> bool:
        return self.password_hash == User.hash_password(password, self.salt)


class DetectionHistory(Base):
    __tablename__ = "detection_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    watchlist_hit: Mapped[bool] = mapped_column(default=False)
    snapshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    user: Mapped["User"] = relationship(back_populates="detection_history")


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    added_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        ensure_storage_dirs()
        db_path = get_db_path()
        _engine = create_engine(f"sqlite:///{db_path}", echo=False)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN created_by_admin_id INTEGER REFERENCES users(id)"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(100) NOT NULL DEFAULT ''"))
            conn.commit()
        except Exception:
            pass
    
    create_default_admin()


def create_default_admin() -> None:
    session = get_session()
    try:
        existing_admin = session.query(User).filter(User.username == "admin").first()
        if existing_admin is None:
            admin = User(
                username="admin",
                full_name="System Administrator",
                password_hash=User.hash_password("admin123", "adminSalt2024"),
                salt="adminSalt2024",
                role="admin",
                is_active=True,
            )
            session.add(admin)
            session.commit()
            LOGGER.info("Default admin user created (username: admin, password: admin123)")
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to create default admin: %s", e)
    finally:
        session.close()


def verify_user(username: str, password: str) -> Optional[dict]:
    session = get_session()
    try:
        user = session.query(User).filter(User.username == username, User.is_active == True).first()
        if user and user.verify_password(password):
            user.last_login = datetime.now()
            session.commit()
            return {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name or user.username,
                "role": user.role,
                "created_by_admin_id": user.created_by_admin_id,
            }
        return None
    finally:
        session.close()


def create_user(
    username: str,
    password: str,
    role: str = "gate keeper",
    created_by_admin_id: Optional[int] = None,
    full_name: str = "",
) -> Optional[User]:
    session = get_session()
    try:
        existing = session.query(User).filter(User.username == username).first()
        if existing:
            return None

        salt = secrets.token_hex(16)
        user = User(
            username=username,
            full_name=full_name.strip() or username,
            password_hash=User.hash_password(password, salt),
            salt=salt,
            role=role,
            created_by_admin_id=created_by_admin_id,
            is_active=True,
        )
        session.add(user)
        session.commit()
        return user
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to create user: %s", e)
        return None
    finally:
        session.close()


def update_user_password(user_id: int, new_password: str) -> bool:
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.salt = secrets.token_hex(16)
            user.password_hash = User.hash_password(new_password, user.salt)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to update password: %s", e)
        return False
    finally:
        session.close()


def get_users_by_admin(admin_id: int) -> list[User]:
    session = get_session()
    try:
        return session.query(User).filter(User.created_by_admin_id == admin_id).all()
    finally:
        session.close()


def get_user_by_id(user_id: int) -> Optional[User]:
    session = get_session()
    try:
        return session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()


def user_exists(username: str) -> bool:
    session = get_session()
    try:
        return session.query(User).filter(User.username == username).first() is not None
    finally:
        session.close()


def admin_exists() -> bool:
    session = get_session()
    try:
        return session.query(User).filter(User.role == "admin").first() is not None
    finally:
        session.close()


def get_all_users() -> list[User]:
    session = get_session()
    try:
        return session.query(User).all()
    finally:
        session.close()


def update_user_role(user_id: int, role: str) -> bool:
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user:
            user.role = role
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to update user role: %s", e)
        return False
    finally:
        session.close()


def delete_user(user_id: int) -> bool:
    session = get_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if user and user.username != "admin":
            session.delete(user)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to delete user: %s", e)
        return False
    finally:
        session.close()


def add_detection_history(
    user_id: int,
    plate_number: str,
    confidence: Optional[float],
    source: str,
    watchlist_hit: bool = False,
    snapshot_path: Optional[str] = None,
) -> DetectionHistory:
    session = get_session()
    try:
        history = DetectionHistory(
            user_id=user_id,
            plate_number=plate_number,
            confidence=confidence,
            source=source,
            watchlist_hit=watchlist_hit,
            snapshot_path=snapshot_path,
        )
        session.add(history)
        session.commit()
        return history
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to add detection history: %s", e)
        return None
    finally:
        session.close()


def get_detection_history(
    user_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[DetectionHistory]:
    session = get_session()
    try:
        query = session.query(DetectionHistory)
        if user_id:
            query = query.filter(DetectionHistory.user_id == user_id)
        return query.order_by(DetectionHistory.timestamp.desc()).offset(offset).limit(limit).all()
    finally:
        session.close()


def add_snapshot(
    user_id: int,
    plate_number: str,
    file_path: str,
    source: Optional[str] = None,
) -> Snapshot:
    session = get_session()
    try:
        snapshot = Snapshot(
            user_id=user_id,
            plate_number=plate_number,
            file_path=file_path,
            source=source,
        )
        session.add(snapshot)
        session.commit()
        return snapshot
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to add snapshot: %s", e)
        return None
    finally:
        session.close()


def get_snapshots(user_id: Optional[int] = None, limit: int = 50) -> list[Snapshot]:
    session = get_session()
    try:
        query = session.query(Snapshot)
        if user_id:
            query = query.filter(Snapshot.user_id == user_id)
        return query.order_by(Snapshot.created_at.desc()).limit(limit).all()
    finally:
        session.close()


def add_watchlist_plate(plate_number: str, added_by: int, notes: Optional[str] = None) -> bool:
    session = get_session()
    try:
        existing = session.query(Watchlist).filter(Watchlist.plate_number == plate_number.upper()).first()
        if existing:
            return False

        watchlist_item = Watchlist(
            plate_number=plate_number.upper(),
            added_by=added_by,
            notes=notes,
        )
        session.add(watchlist_item)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to add watchlist plate: %s", e)
        return False
    finally:
        session.close()


def get_watchlist() -> list[Watchlist]:
    session = get_session()
    try:
        return session.query(Watchlist).order_by(Watchlist.added_at.desc()).all()
    finally:
        session.close()


def remove_watchlist_plate(plate_number: str) -> bool:
    session = get_session()
    try:
        item = session.query(Watchlist).filter(Watchlist.plate_number == plate_number.upper()).first()
        if item:
            session.delete(item)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to remove watchlist plate: %s", e)
        return False
    finally:
        session.close()


def is_watchlist_hit(plate_number: str) -> bool:
    session = get_session()
    try:
        return (
            session.query(Watchlist)
            .filter(Watchlist.plate_number == plate_number.upper())
            .first()
            is not None
        )
    finally:
        session.close()
