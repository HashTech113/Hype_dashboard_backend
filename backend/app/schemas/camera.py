from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import CameraType
from app.schemas.common import ORMModel

_ALLOWED_SCHEMES = ("rtsp://", "rtsps://", "http://", "https://")

# Characters that MUST be percent-encoded when they appear in the userinfo
# segment of a URL (RFC 3986 §3.2.1 — userinfo). If the user pastes a real-
# world camera password containing any of these, the URL silently misparses
# and OpenCV fails with a useless error. We auto-fix at validation time.
_USERINFO_RESERVED = set("@:/?#[]")


def _sanitize_rtsp_url(raw: str) -> str:
    """Strip whitespace, then if the userinfo segment contains an unencoded
    reserved char (e.g. a raw '@' inside the password), percent-encode it.

    Idempotent — already-encoded URLs pass through unchanged.

    Returns the sanitized URL. Raises ValueError if no rescue is possible.
    """
    v = raw.strip().replace("\n", "").replace("\r", "")
    if not v:
        raise ValueError("rtsp_url must not be empty")

    lowered = v.lower()
    if not any(lowered.startswith(s) for s in _ALLOWED_SCHEMES):
        raise ValueError(
            f"rtsp_url must start with one of: {', '.join(_ALLOWED_SCHEMES)}. "
            f"Got: {v[:40]!r}"
        )

    # Split scheme://userinfo@host/path  — but tolerate multiple '@'s in
    # userinfo because that's exactly the bug class we're fixing.
    scheme_end = v.index("://") + 3
    scheme = v[:scheme_end]
    rest = v[scheme_end:]

    # Find the LAST '@' before the first '/' (or end). Everything before
    # the last '@' is userinfo; everything after is the host+path. If the
    # password itself contains '@' the user has the right INTENT but the
    # WRONG encoding — we re-encode the userinfo segment.
    path_start = len(rest)
    for i, c in enumerate(rest):
        if c == "/":
            path_start = i
            break

    auth_segment = rest[:path_start]
    host_and_path = rest[path_start:]

    if "@" not in auth_segment:
        # No credentials embedded — nothing to fix here.
        return scheme + rest

    last_at = auth_segment.rfind("@")
    userinfo = auth_segment[:last_at]
    host = auth_segment[last_at + 1 :]

    # If there are MORE than one '@' in userinfo, the inner ones belong to
    # the password and must be %40. Similarly other reserved chars inside
    # userinfo get percent-encoded. We split user:password at the first ':'.
    if ":" in userinfo:
        user, _, password = userinfo.partition(":")
    else:
        user, password = userinfo, ""

    def needs_encoding(s: str) -> bool:
        return any(c in _USERINFO_RESERVED for c in s)

    if needs_encoding(user) or needs_encoding(password):
        # quote() leaves '/' untouched by default; we want it encoded inside
        # userinfo, so pass safe="" — every reserved char gets %xx-encoded.
        user_enc = quote(user, safe="")
        pass_enc = quote(password, safe="")
        userinfo_fixed = f"{user_enc}:{pass_enc}" if pass_enc or ":" in userinfo else user_enc
        return f"{scheme}{userinfo_fixed}@{host}{host_and_path}"

    return v


def _validate_rtsp(v: str | None) -> str | None:
    if v is None:
        return v
    return _sanitize_rtsp_url(v)


class CameraBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    rtsp_url: str = Field(min_length=1, max_length=1024)
    camera_type: CameraType
    location: str | None = Field(default=None, max_length=256)
    description: str | None = None
    fps_override: int | None = Field(
        default=None,
        ge=1,
        le=30,
        description="Per-camera FPS override. NULL = use the global CAMERA_FPS setting.",
    )

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
    fps_override: int | None = Field(default=None, ge=1, le=30)

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
    fps_override: int | None = None
    created_at: datetime
    updated_at: datetime
    # H9 fix: populated by create/update/delete handlers when the DB row
    # persisted but the camera worker could not be started or stopped.
    # Frontend uses it to surface a warning toast (e.g. "Camera saved,
    # but the worker did not start: <reason>") instead of silently
    # leaving the operator thinking everything succeeded.
    worker_warning: str | None = None


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
    seconds_since_start: float | None = None
    processed_frames: int = 0
    # Ops / debug fields populated by the new resilient reader+manager.
    consecutive_open_failures: int = 0
    consecutive_read_failures: int = 0
    total_reconnects: int = 0
    health_state: str = "UNKNOWN"  # CONNECTING / STREAMING / FLAPPING / DEGRADED
    fps_effective: int | None = None
    fps_override: int | None = None
    # Native FPS auto-detected from the RTSP stream (cv2.CAP_PROP_FPS).
    # Null until the camera opens successfully at least once. The worker
    # uses this as its read rate by default so latency tracks the
    # camera's actual frame production rate.
    fps_detected: float | None = None
    lifetime_restarts: int = 0
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


# ----------------------------------------------------------------------
# SmartConnect — the user-friendly camera setup endpoint
# ----------------------------------------------------------------------


class SmartConnectRequest(BaseModel):
    """Smart-connect a camera. Either give us a URL OR (host + credentials).

    If both URL and host are given, we try the URL first; if it fails, we
    fall back to host-credential auto-discovery.

    The metadata fields (name, camera_type, location, description) are
    OPTIONAL because the same schema is shared by `/smart-probe` (which
    only tests the connection and never persists anything) and
    `/connect-smart` (which DOES persist). Connect-smart adds its own
    runtime check that `name` is present before saving.
    """

    # Camera metadata — optional so /smart-probe accepts a connection-only
    # payload. /connect-smart enforces name at the handler level.
    name: str | None = Field(default=None, max_length=128)
    # ENTRY by default — the UI no longer exposes this field because we
    # don't model turnstile-style direction. Keeping the column with a
    # sane default preserves DB compat without forcing the operator to
    # think about it.
    camera_type: CameraType = Field(default=CameraType.ENTRY)
    location: str | None = Field(default=None, max_length=256)
    description: str | None = None
    is_active: bool = True
    fps_override: int | None = Field(default=None, ge=1, le=30)

    # Connection — at least one of (rtsp_url) or (host + credentials)
    rtsp_url: str | None = Field(default=None, max_length=1024)
    host: str | None = Field(default=None, max_length=255)
    port: int = Field(default=554, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=128)

    # Knobs
    prefer_sub_stream: bool = Field(
        default=True,
        description="Use the lowest-resolution profile (lighter on CPU, plenty for face detection).",
    )
    probe_timeout_seconds: int = Field(default=15, ge=3, le=60)

    @field_validator("rtsp_url")
    @classmethod
    def _rtsp_fmt(cls, v: str | None) -> str | None:
        return _validate_rtsp(v)

    @model_validator(mode="after")
    def _need_something(self):
        if not self.rtsp_url and not self.host:
            raise ValueError(
                "Provide either rtsp_url, or host + username + password (so we can auto-discover)."
            )
        return self


class SmartProbeStep(BaseModel):
    name: str
    ok: bool
    duration_ms: int
    detail: str
    error: str | None = None


class SmartProbeResult(BaseModel):
    ok: bool
    working_url: str | None = None
    width: int | None = None
    height: int | None = None
    strategy: str  # "user_url" | "user_url_autofixed" | "onvif_discovery" | "vendor_fallback"
    vendor_hint: str | None = None
    steps: list[SmartProbeStep]
    summary: str
    suggestion: str | None = None


class SmartConnectResult(BaseModel):
    camera: CameraRead | None = None
    probe: SmartProbeResult
