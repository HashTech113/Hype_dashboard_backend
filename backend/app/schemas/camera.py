from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.constants import CameraType
from app.schemas.common import ORMModel

_ALLOWED_SCHEMES = ("rtsp://", "rtsps://", "http://", "https://")


def _validate_rtsp(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("rtsp_url must not be empty")
    lowered = v.lower()
    if not any(lowered.startswith(s) for s in _ALLOWED_SCHEMES):
        raise ValueError(
            f"rtsp_url must start with one of: {', '.join(_ALLOWED_SCHEMES)}"
        )
    return v


class CameraBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    rtsp_url: str = Field(min_length=1, max_length=1024)
    camera_type: CameraType
    location: str | None = Field(default=None, max_length=256)
    description: str | None = None

    @field_validator("rtsp_url")
    @classmethod
    def _rtsp_fmt(cls, v: str) -> str:
        return _validate_rtsp(v)  # type: ignore[return-value]


class CameraCreate(CameraBase):
    is_active: bool = True


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    rtsp_url: str | None = Field(default=None, min_length=1, max_length=1024)
    camera_type: CameraType | None = None
    location: str | None = Field(default=None, max_length=256)
    description: str | None = None
    is_active: bool | None = None

    @field_validator("rtsp_url")
    @classmethod
    def _rtsp_fmt(cls, v: str | None) -> str | None:
        return _validate_rtsp(v)


class CameraRead(ORMModel):
    id: int
    name: str
    rtsp_url: str
    camera_type: CameraType
    location: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CameraHealth(BaseModel):
    id: int
    name: str
    is_active: bool
    is_running: bool
    last_heartbeat_age_seconds: float | None
    # None until a frame is actually received. The frontend uses this —
    # not `last_heartbeat_age_seconds` — to label a camera "Live", because
    # the heartbeat keeps ticking even while RTSP reads silently fail.
    last_frame_age_seconds: float | None = None
    processed_frames: int = 0
    last_error: str | None


class CameraProbeRequest(BaseModel):
    rtsp_url: str = Field(min_length=1, max_length=1024)
    timeout_ms: int = Field(default=5000, ge=500, le=30000)

    @field_validator("rtsp_url")
    @classmethod
    def _rtsp_fmt(cls, v: str) -> str:
        return _validate_rtsp(v)  # type: ignore[return-value]


class CameraProbeResult(BaseModel):
    ok: bool
    width: int | None = None
    height: int | None = None
    elapsed_ms: int
    error: str | None = None
