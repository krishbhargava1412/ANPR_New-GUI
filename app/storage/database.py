from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.storage import get_database_url

LOGGER = logging.getLogger("anpr_new_gui.storage.database")
AVAILABLE_USER_ROLES = [
    "gate keeper",
    "manager",
    "operator",
    "viewer",
    "admin",
]


# ── ORM Base ─────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Models ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    detection_history: Mapped[list["DetectionLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        ).hex()

    def verify_password(self, password: str) -> bool:
        return self.password_hash == User.hash_password(password, self.salt)


class DetectionLog(Base):
    """Replaces the CSV-based detected_plates_log.csv."""

    __tablename__ = "detection_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    plate_number: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    watchlist_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("snapshots.id"), nullable=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    user: Mapped[Optional["User"]] = relationship(back_populates="detection_history")

    __table_args__ = (
        Index("idx_detection_log_plate", "plate_number"),
        Index("idx_detection_log_ts", "timestamp"),
    )


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    plate_number: Mapped[str] = mapped_column(String(20), nullable=False)
    image_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="image/png"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plate_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    added_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppSettings(Base):
    """Replaces ui_settings.json — stores settings as JSONB."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class CaseFlag(Base):
    """Replaces case_flags.json."""

    __tablename__ = "case_flags"

    plate_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class ShareSession(Base):
    __tablename__ = "share_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    owner_username: Mapped[str] = mapped_column(String(100), nullable=False)
    camera_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    socket_event: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_share_sessions_active", "is_shared"),
        Index("idx_share_sessions_socket_event", "socket_event"),
    )


# ── Engine / Session ─────────────────────────────────────

_engine = None
_SessionLocal = None


def _format_database_error(url: str, exc: Exception) -> RuntimeError:
    message = (
        "Database startup failed. PostgreSQL is not reachable at "
        f"{url}. Start the database first with "
        "`docker compose up -d postgres`, or update DATABASE_URL in .env "
        "to a running PostgreSQL instance."
    )
    error = RuntimeError(message)
    error.__cause__ = exc
    return error


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        _engine = create_engine(url, echo=False, pool_pre_ping=True)
    return _engine


def get_session():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db() -> None:
    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        Base.metadata.create_all(engine)
    except OperationalError as exc:
        raise _format_database_error(get_database_url(), exc)
    create_default_admin()


# ── User CRUD ────────────────────────────────────────────

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
            LOGGER.info(
                "Default admin user created (username: admin, password: admin123)"
            )
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to create default admin: %s", e)
    finally:
        session.close()


def verify_user(username: str, password: str) -> Optional[dict]:
    session = get_session()
    try:
        user = (
            session.query(User)
            .filter(User.username == username, User.is_active == True)
            .first()
        )
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
        return (
            session.query(User)
            .filter(User.created_by_admin_id == admin_id)
            .all()
        )
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
        return (
            session.query(User).filter(User.username == username).first() is not None
        )
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


# ── Detection Log CRUD (replaces CSV) ────────────────────

def add_detection_log(
    plate_number: str,
    source: str,
    confidence: Optional[float] = None,
    watchlist_hit: bool = False,
    snapshot_id: Optional[int] = None,
    user_id: Optional[int] = None,
    timestamp: Optional[datetime] = None,
) -> Optional[DetectionLog]:
    session = get_session()
    try:
        entry = DetectionLog(
            timestamp=timestamp or datetime.now(),
            plate_number=plate_number,
            source=source,
            confidence=confidence,
            watchlist_hit=watchlist_hit,
            snapshot_id=snapshot_id,
            user_id=user_id,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to add detection log: %s", e)
        return None
    finally:
        session.close()


def search_detection_log(
    plate: str = "",
    source_filter: str = "",
    watchlist_only: bool = False,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    conf_min: Optional[float] = None,
    conf_max: Optional[float] = None,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    session = get_session()
    try:
        query = session.query(DetectionLog).order_by(DetectionLog.timestamp.asc())

        if plate:
            query = query.filter(
                DetectionLog.plate_number.ilike(f"%{plate.upper()}%")
            )
        if source_filter:
            query = query.filter(
                DetectionLog.source.ilike(f"%{source_filter}%")
            )
        if watchlist_only:
            query = query.filter(DetectionLog.watchlist_hit == True)
        if from_date:
            query = query.filter(DetectionLog.timestamp >= from_date)
        if to_date:
            query = query.filter(DetectionLog.timestamp <= to_date)
        if conf_min is not None:
            query = query.filter(DetectionLog.confidence >= conf_min)
        if conf_max is not None:
            query = query.filter(DetectionLog.confidence <= conf_max)

        rows = query.limit(limit).all()
        results = []
        for row in rows:
            results.append({
                "id": row.id,
                "timestamp": row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp_dt": row.timestamp,
                "plate": row.plate_number,
                "source": row.source,
                "confidence": row.confidence,
                "watchlist_hit": row.watchlist_hit,
                "snapshot_id": row.snapshot_id,
                "user_id": row.user_id,
            })
        return results
    finally:
        session.close()


def count_detection_log(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
) -> int:
    session = get_session()
    try:
        query = session.query(func.count(DetectionLog.id))
        if from_date:
            query = query.filter(DetectionLog.timestamp >= from_date)
        if to_date:
            query = query.filter(DetectionLog.timestamp <= to_date)
        return query.scalar() or 0
    finally:
        session.close()


def clear_detection_log() -> None:
    session = get_session()
    try:
        session.query(DetectionLog).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to clear detection log: %s", e)
    finally:
        session.close()


def delete_detection_entries(entry_ids: list[int]) -> int:
    session = get_session()
    try:
        deleted = (
            session.query(DetectionLog)
            .filter(DetectionLog.id.in_(entry_ids))
            .delete(synchronize_session="fetch")
        )
        session.commit()
        return deleted
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to delete detection entries: %s", e)
        return 0
    finally:
        session.close()


# ── Snapshot CRUD ────────────────────────────────────────

def add_snapshot_blob(
    plate_number: str,
    image_data: bytes,
    source: Optional[str] = None,
    user_id: Optional[int] = None,
    content_type: str = "image/png",
) -> Optional[int]:
    """Store a snapshot image as BYTEA in PostgreSQL. Returns snapshot id."""
    session = get_session()
    try:
        snapshot = Snapshot(
            user_id=user_id,
            plate_number=plate_number,
            image_data=image_data,
            content_type=content_type,
            source=source,
        )
        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)
        return snapshot.id
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to add snapshot: %s", e)
        return None
    finally:
        session.close()


def get_snapshot_image(snapshot_id: int) -> Optional[tuple[bytes, str]]:
    """Return (image_bytes, content_type) or None."""
    session = get_session()
    try:
        snap = session.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
        if snap and snap.image_data:
            return snap.image_data, snap.content_type
        return None
    finally:
        session.close()


def delete_snapshot(snapshot_id: int) -> bool:
    session = get_session()
    try:
        snap = session.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
        if snap:
            session.delete(snap)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to delete snapshot: %s", e)
        return False
    finally:
        session.close()


def clear_all_snapshots() -> int:
    session = get_session()
    try:
        count = session.query(Snapshot).delete()
        session.commit()
        return count
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to clear snapshots: %s", e)
        return 0
    finally:
        session.close()


# ── Watchlist CRUD ───────────────────────────────────────

def add_watchlist_plate(
    plate_number: str, added_by: Optional[int] = None, notes: Optional[str] = None
) -> bool:
    session = get_session()
    try:
        existing = (
            session.query(Watchlist)
            .filter(Watchlist.plate_number == plate_number.upper())
            .first()
        )
        if existing:
            return False
        item = Watchlist(
            plate_number=plate_number.upper(),
            added_by=added_by,
            notes=notes,
        )
        session.add(item)
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


def get_watchlist_plates() -> set[str]:
    """Return set of all watchlist plate numbers."""
    session = get_session()
    try:
        rows = session.query(Watchlist.plate_number).all()
        return {row[0] for row in rows}
    finally:
        session.close()


def remove_watchlist_plate(plate_number: str) -> bool:
    session = get_session()
    try:
        item = (
            session.query(Watchlist)
            .filter(Watchlist.plate_number == plate_number.upper())
            .first()
        )
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


# ── App Settings CRUD (replaces ui_settings.json) ───────

def get_settings(key: str = "ui") -> dict[str, Any]:
    session = get_session()
    try:
        row = session.query(AppSettings).filter(AppSettings.key == key).first()
        if row:
            return row.value
        return {}
    finally:
        session.close()


def set_settings(key: str, value: dict[str, Any]) -> None:
    session = get_session()
    try:
        row = session.query(AppSettings).filter(AppSettings.key == key).first()
        if row:
            row.value = value
            row.updated_at = datetime.now()
        else:
            row = AppSettings(key=key, value=value)
            session.add(row)
        session.commit()
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to set settings: %s", e)
    finally:
        session.close()


# ── Case Flags CRUD (replaces case_flags.json) ──────────

def get_case_flags() -> dict[str, dict[str, Any]]:
    session = get_session()
    try:
        rows = session.query(CaseFlag).all()
        return {
            row.plate_number: {
                "flagged": row.flagged,
                "note": row.note or "",
                "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                if row.updated_at
                else "",
            }
            for row in rows
        }
    finally:
        session.close()


def set_case_flag(
    plate_number: str, flagged: bool, note: str = ""
) -> None:
    session = get_session()
    try:
        cleaned = plate_number.upper().strip()
        if not cleaned:
            return
        row = (
            session.query(CaseFlag)
            .filter(CaseFlag.plate_number == cleaned)
            .first()
        )
        if row:
            row.flagged = flagged
            row.note = note.strip()
            row.updated_at = datetime.now()
        else:
            row = CaseFlag(
                plate_number=cleaned,
                flagged=flagged,
                note=note.strip(),
            )
            session.add(row)
        session.commit()
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to set case flag: %s", e)
    finally:
        session.close()


def share_session_to_dict(row: ShareSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "owner_username": row.owner_username,
        "camera_id": row.camera_id,
        "label": row.label,
        "socket_event": row.socket_event,
        "isShared": row.is_shared,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
    }


def create_share_session(
    *,
    owner_user_id: Optional[int],
    owner_username: str,
    camera_id: int,
    label: str,
    socket_event: str,
) -> Optional[dict[str, Any]]:
    session = get_session()
    try:
        existing = (
            session.query(ShareSession)
            .filter(
                ShareSession.owner_username == owner_username,
                ShareSession.camera_id == camera_id,
                ShareSession.is_shared == True,
            )
            .first()
        )
        if existing:
            existing.owner_user_id = owner_user_id
            existing.label = label
            existing.socket_event = socket_event
            existing.started_at = datetime.now()
            existing.ended_at = None
            session.commit()
            session.refresh(existing)
            return share_session_to_dict(existing)

        row = ShareSession(
            owner_user_id=owner_user_id,
            owner_username=owner_username,
            camera_id=camera_id,
            label=label,
            socket_event=socket_event,
            is_shared=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return share_session_to_dict(row)
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to create share session: %s", e)
        return None
    finally:
        session.close()


def stop_share_session(
    *,
    socket_event: Optional[str] = None,
    owner_username: Optional[str] = None,
    camera_id: Optional[int] = None,
) -> bool:
    session = get_session()
    try:
        query = session.query(ShareSession).filter(ShareSession.is_shared == True)
        if socket_event:
            query = query.filter(ShareSession.socket_event == socket_event)
        if owner_username:
            query = query.filter(ShareSession.owner_username == owner_username)
        if camera_id is not None:
            query = query.filter(ShareSession.camera_id == camera_id)
        row = query.first()
        if row is None:
            return False
        row.is_shared = False
        row.ended_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        LOGGER.error("Failed to stop share session: %s", e)
        return False
    finally:
        session.close()


def get_share_session(socket_event: str) -> Optional[dict[str, Any]]:
    session = get_session()
    try:
        row = (
            session.query(ShareSession)
            .filter(ShareSession.socket_event == socket_event)
            .first()
        )
        if row is None:
            return None
        return share_session_to_dict(row)
    finally:
        session.close()


def list_active_share_sessions() -> list[dict[str, Any]]:
    session = get_session()
    try:
        rows = (
            session.query(ShareSession)
            .filter(ShareSession.is_shared == True)
            .order_by(ShareSession.started_at.desc())
            .all()
        )
        return [share_session_to_dict(row) for row in rows]
    finally:
        session.close()
