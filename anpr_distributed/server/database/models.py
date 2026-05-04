"""
SQLAlchemy 2.0 models for PostgreSQL.

Migrated from SQLite models in app/storage/database.py.
Key changes:
  - PostgreSQL-native types (TIMESTAMPTZ, JSONB, INET, ARRAY)
  - Separate Camera entity (was JSON strings in settings)
  - Audit log table (was flat log file)
  - Argon2 password hashing (was PBKDF2)
  - Threat levels on watchlist
  - Detection linked to camera_id instead of user_id
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    # No separate salt column — argon2id embeds salt in the hash string
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="operator",
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    detections: Mapped[list["Detection"]] = relationship(
        back_populates="user", foreign_keys="Detection.recorded_by",
    )
    watchlist_items: Mapped[list["Watchlist"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class Camera(Base):
    """First-class camera entity. Replaces camera_indices + ip_camera_urls from ui_settings.json."""
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="rtsp",
    )
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    added_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )

    # Relationships
    detections: Mapped[list["Detection"]] = relationship(back_populates="camera")


class Detection(Base):
    """Plate detection record. Replaces BOTH detection_history table AND plate_log.csv."""
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cameras.id"), nullable=False, index=True,
    )
    plate_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ocr_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox: Mapped[Optional[list[int]]] = mapped_column(ARRAY(Integer), nullable=True)
    snapshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    watchlist_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict,
    )
    edge_node_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    recorded_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True,
    )

    # Relationships
    camera: Mapped["Camera"] = relationship(back_populates="detections")
    user: Mapped[Optional["User"]] = relationship(
        back_populates="detections", foreign_keys=[recorded_by],
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plate_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    threat_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium",
    )
    added_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="watchlist_items")


class AuditLog(Base):
    """Structured audit trail. Replaces anpr_app.log flat file."""
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")


class CaseFlag(Base):
    """Replaces case_flags.json file."""
    __tablename__ = "case_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plate_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[Optional[str]] = mapped_column(Text, default="")
    flagged_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
