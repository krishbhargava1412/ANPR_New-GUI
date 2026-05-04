"""
Pydantic models shared between edge (Jetson) and server (DRDO).

These define the exact JSON payloads exchanged over the REST API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Edge → Server Payloads ────────────────────────────────────────────────────
class DetectionPayload(BaseModel):
    """Single plate detection sent from edge to server."""
    camera_id: str = Field(..., description="Camera identifier (e.g. 'cam_1')")
    plate_number: str = Field(..., description="Normalized plate text")
    confidence: float = Field(..., ge=0.0, le=1.0)
    ocr_score: float = Field(0.0, ge=0.0, le=1.0)
    bbox: list[int] = Field(..., min_length=4, max_length=4, description="[x1, y1, x2, y2]")
    snapshot_b64: Optional[str] = Field(None, description="Base64-encoded JPEG crop")
    detected_at: datetime = Field(default_factory=datetime.now)
    watchlist_hit: bool = False
    edge_node_id: str = Field("jetson-01", description="Identifier for the edge device")


class DetectionBatchPayload(BaseModel):
    """Batch of detections pushed from edge to server."""
    detections: list[DetectionPayload]
    edge_node_id: str = "jetson-01"
    batch_timestamp: datetime = Field(default_factory=datetime.now)


class EdgeHeartbeat(BaseModel):
    """Periodic health check from edge to server."""
    edge_node_id: str = "jetson-01"
    active_cameras: int = 0
    gpu_temp_celsius: Optional[float] = None
    gpu_utilization_pct: Optional[float] = None
    uptime_seconds: float = 0.0
    inference_fps: float = 0.0
    queue_depth: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


# ── Server → Edge Payloads ────────────────────────────────────────────────────
class WatchlistSyncResponse(BaseModel):
    """Watchlist data pushed from server to edge for local caching."""
    plates: list[str]
    version: int = 0
    updated_at: datetime = Field(default_factory=datetime.now)


# ── Auth Payloads ─────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    full_name: str
    role: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── User Management ──────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: str = ""
    role: str = Field("operator", pattern="^(admin|manager|operator|gate_keeper|viewer)$")


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(admin|manager|operator|gate_keeper|viewer)$")
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Camera Management ────────────────────────────────────────────────────────
class CameraCreate(BaseModel):
    name: str
    source_url: str
    source_type: str = Field("rtsp", pattern="^(rtsp|onvif|usb|file)$")
    location: Optional[str] = None


class CameraResponse(BaseModel):
    id: int
    name: str
    source_url: str
    source_type: str
    location: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


# ── Watchlist ─────────────────────────────────────────────────────────────────
class WatchlistCreate(BaseModel):
    plate_number: str = Field(..., min_length=4, max_length=20)
    threat_level: str = Field("medium", pattern="^(low|medium|high|critical)$")
    notes: Optional[str] = None


class WatchlistResponse(BaseModel):
    id: int
    plate_number: str
    threat_level: str
    added_by: int
    notes: Optional[str]
    added_at: datetime

    class Config:
        from_attributes = True


# ── Detection History ─────────────────────────────────────────────────────────
class DetectionResponse(BaseModel):
    id: int
    camera_id: int
    plate_number: str
    confidence: Optional[float]
    ocr_score: Optional[float]
    snapshot_path: Optional[str]
    watchlist_hit: bool
    detected_at: datetime

    class Config:
        from_attributes = True


# ── Dashboard Stats ──────────────────────────────────────────────────────────
class DashboardStats(BaseModel):
    total_detections: int = 0
    unique_plates: int = 0
    watchlist_hits: int = 0
    active_cameras: int = 0
    recent_rate_per_min: float = 0.0
    avg_confidence: Optional[float] = None
    trend_delta: str = "+0 plates/min"
    trend_direction: str = "up"
