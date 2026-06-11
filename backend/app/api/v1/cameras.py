from __future__ import annotations

import asyncio
import time

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_camera_manager,
    get_current_admin,
    get_db,
    require_roles,
)
from app.core.constants import Role
from app.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    NotFoundError,
)
from app.core.logger import get_logger
from app.models.admin import Admin
from app.models.camera import Camera
from app.repositories.camera_repo import CameraRepository
from app.schemas.camera import (
    CameraCreate,
    CameraHealth,
    CameraProbeRequest,
    CameraProbeResult,
    CameraRead,
    CameraUpdate,
    SmartConnectRequest,
    SmartConnectResult,
    SmartProbeResult,
    SmartProbeStep,
)
from app.services.camera_discovery_service import (
    DiscoveredCamera,
    discover_cameras,
)
from app.services.go2rtc_service import get_go2rtc_service
from app.services.smart_rtsp_service import (
    SmartProbeRequest as _SmartProbeRequest,
    get_smart_rtsp_service,
)
from app.workers.camera_manager import CameraManager
from app.workers.rtsp_probe import probe_rtsp

router = APIRouter(prefix="/cameras", tags=["cameras"])
log = get_logger(__name__)


def _resync_go2rtc(camera_id: int, rtsp_url: str | None, *, removed: bool = False) -> None:
    """Notify go2rtc bridge of camera config changes. Non-blocking:
    failure to sync just means WebRTC falls back to WebSocket — never
    breaks the camera CRUD flow."""
    try:
        svc = get_go2rtc_service()
        if not svc.is_running:
            return
        if removed:
            svc.remove_camera(camera_id)
        elif rtsp_url:
            svc.sync_cameras([(camera_id, rtsp_url)])
    except Exception:
        log.debug("go2rtc sync skipped: %s", camera_id, exc_info=True)


def _try_restart_with_warning(
    manager: CameraManager,
    camera_id: int,
    action: str,
    *,
    skip_probe: bool = False,
) -> str | None:
    """Run manager.restart() and translate any failure into a UI-friendly
    warning string (H9 fix). Returns None on success. AppError messages
    are passed through (they're written for users). Generic exceptions
    log a full traceback and return a generic message.
    """
    from app.core.exceptions import AppError

    try:
        manager.restart(camera_id, skip_probe=skip_probe)
        return None
    except AppError as exc:
        log.warning(
            "Worker %s for camera id=%s reported: %s",
            action, camera_id, exc.message,
        )
        return exc.message
    except Exception as exc:
        log.exception("Failed to %s worker for camera id=%s", action, camera_id)
        return (
            f"Camera saved, but the worker could not {action}. "
            f"Use Restart from the row menu after fixing the cause. "
            f"({type(exc).__name__})"
        )


@router.get("", response_model=list[CameraRead])
def list_cameras(
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> list[CameraRead]:
    return [CameraRead.model_validate(c) for c in CameraRepository(db).list_all()]


@router.get("/health", response_model=list[CameraHealth])
def cameras_health(
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(get_current_admin),
) -> list[CameraHealth]:
    statuses = {s["camera_id"]: s for s in manager.status()}
    result: list[CameraHealth] = []
    for cam in CameraRepository(db).list_all():
        s = statuses.get(cam.id)
        result.append(
            CameraHealth(
                id=cam.id,
                name=cam.name,
                is_active=cam.is_active,
                is_running=bool(s and s["is_running"]),
                last_heartbeat_age_seconds=s["last_heartbeat_age_seconds"] if s else None,
                last_frame_age_seconds=s["last_frame_age_seconds"] if s else None,
                seconds_since_start=s["seconds_since_start"] if s else None,
                processed_frames=int(s["processed_frames"]) if s else 0,
                consecutive_open_failures=int(s["consecutive_open_failures"]) if s else 0,
                consecutive_read_failures=int(s["consecutive_read_failures"]) if s else 0,
                total_reconnects=int(s["total_reconnects"]) if s else 0,
                health_state=s["health_state"] if s else "STOPPED",
                fps_effective=s["fps_effective"] if s else None,
                fps_override=s["fps_override"] if s else getattr(cam, "fps_override", None),
                fps_detected=s.get("fps_detected") if s else None,
                lifetime_restarts=int(s["lifetime_restarts"]) if s else 0,
                last_error=s["last_error"] if s else None,
            )
        )
    return result


@router.post("/probe", response_model=CameraProbeResult)
async def probe_camera(
    payload: CameraProbeRequest,
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> CameraProbeResult:
    outcome = await run_in_threadpool(
        probe_rtsp, payload.rtsp_url, timeout_ms=payload.timeout_ms
    )
    return CameraProbeResult(
        ok=outcome.ok,
        width=outcome.width,
        height=outcome.height,
        elapsed_ms=outcome.elapsed_ms,
        error=outcome.error,
    )


@router.post("/discover")
async def discover_cameras_on_lan(
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> dict:
    """Scan the local network for cameras.

    Runs in two phases:
      1. ONVIF WS-Discovery multicast probe (cameras self-identify if enabled)
      2. TCP port-554 scan across all local /24 subnets + 192.168.1.x

    Returns each device found with its IP, source ("onvif" or "tcp_scan"),
    vendor hint (when ONVIF responded), and any notes. The operator then
    clicks one to launch Smart Connect with that IP pre-filled.

    Discovery does NOT persist anything — credentials still come from the
    operator via Smart Connect.
    """
    found = await run_in_threadpool(
        discover_cameras,
        include_subnet_scan=True,
        ws_timeout=4.0,
    )
    return {
        "count": len(found),
        "cameras": [
            {
                "ip": c.ip,
                "source": c.source,
                "onvif_url": c.onvif_url,
                "rtsp_port": c.rtsp_port,
                "web_port": c.web_port,
                "vendor_hint": c.vendor_hint,
                "notes": c.notes,
            }
            for c in found
        ],
    }


@router.post("/smart-probe", response_model=SmartProbeResult)
async def smart_probe(
    payload: SmartConnectRequest,
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> SmartProbeResult:
    """Dry-run a smart probe WITHOUT creating a camera.

    Returns the step-by-step diagnostic. Used by the Camera Wizard to give
    the operator live feedback before they commit.
    """
    svc = get_smart_rtsp_service()
    req = _SmartProbeRequest(
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        rtsp_url=payload.rtsp_url,
        prefer_sub_stream=payload.prefer_sub_stream,
        probe_timeout_seconds=payload.probe_timeout_seconds,
    )
    result = await run_in_threadpool(svc.probe, req)
    return SmartProbeResult(
        ok=result.ok,
        working_url=result.working_url,
        width=result.width,
        height=result.height,
        strategy=result.strategy,
        vendor_hint=result.vendor_hint,
        steps=[SmartProbeStep(**s.as_dict()) for s in result.steps],
        summary=result.summary,
        suggestion=result.suggestion,
    )


@router.post("/connect-smart", response_model=SmartConnectResult, status_code=201)
async def connect_smart(
    payload: SmartConnectRequest,
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> SmartConnectResult:
    """Smart-connect a camera in one shot.

    Runs the full discovery ladder, and ONLY if a working URL is found,
    persists a new Camera row + starts the worker. On failure returns the
    diagnostic without writing anything.
    """
    # Name is OPTIONAL on the shared schema (so /smart-probe works without
    # it), but REQUIRED here because we're persisting. Use ValidationError
    # so the existing exception handler produces a clean 422 with a
    # user-friendly message instead of FastAPI's opaque default 422 listing
    # internal field paths.
    if not payload.name or not payload.name.strip():
        from app.core.exceptions import ValidationError
        raise ValidationError(
            message="Please give the camera a name before saving.",
            code="name_required",
        )

    repo = CameraRepository(db)
    if repo.get_by_name(payload.name) is not None:
        raise AlreadyExistsError(f"Camera '{payload.name}' already exists")

    svc = get_smart_rtsp_service()
    req = _SmartProbeRequest(
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        rtsp_url=payload.rtsp_url,
        prefer_sub_stream=payload.prefer_sub_stream,
        probe_timeout_seconds=payload.probe_timeout_seconds,
    )
    result = await run_in_threadpool(svc.probe, req)

    probe_schema = SmartProbeResult(
        ok=result.ok,
        working_url=result.working_url,
        width=result.width,
        height=result.height,
        strategy=result.strategy,
        vendor_hint=result.vendor_hint,
        steps=[SmartProbeStep(**s.as_dict()) for s in result.steps],
        summary=result.summary,
        suggestion=result.suggestion,
    )

    if not result.ok or not result.working_url:
        # Probe failed — return diagnostic without creating the camera.
        return SmartConnectResult(camera=None, probe=probe_schema)

    cam = Camera(
        name=payload.name,
        rtsp_url=result.working_url,
        camera_type=payload.camera_type,
        location=payload.location,
        description=payload.description,
        is_active=payload.is_active,
        fps_override=payload.fps_override,
    )
    repo.add(cam)
    try:
        db.commit()
    except Exception:
        # Race: another admin added a camera with the same name between
        # our duplicate-check and our commit. Roll back and surface as 409.
        db.rollback()
        raise AlreadyExistsError(f"Camera '{payload.name}' already exists")
    response = CameraRead.model_validate(cam)
    if cam.is_active:
        # skip_probe=True — we just probed in the smart-connect path; no need
        # to probe again 50ms later. Also avoids tearing down a freshly-bound
        # worker on a flapping camera.
        warning = _try_restart_with_warning(manager, cam.id, "start", skip_probe=True)
        if warning:
            response.worker_warning = warning
    return SmartConnectResult(camera=response, probe=probe_schema)


@router.get("/{camera_id}", response_model=CameraRead)
def get_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> CameraRead:
    cam = CameraRepository(db).get(camera_id)
    if cam is None:
        raise NotFoundError(f"Camera {camera_id} not found")
    return CameraRead.model_validate(cam)


@router.post("", response_model=CameraRead, status_code=201)
def create_camera(
    payload: CameraCreate,
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> CameraRead:
    repo = CameraRepository(db)
    if repo.get_by_name(payload.name) is not None:
        raise AlreadyExistsError(f"Camera '{payload.name}' already exists")
    cam = Camera(
        name=payload.name,
        rtsp_url=payload.rtsp_url,
        camera_type=payload.camera_type,
        location=payload.location,
        description=payload.description,
        is_active=payload.is_active,
        fps_override=payload.fps_override,
    )
    repo.add(cam)
    db.commit()
    response = CameraRead.model_validate(cam)
    # H9 fix: surface worker-start failures via response.worker_warning so
    # the UI shows a toast instead of "Camera added" + a dead worker.
    if cam.is_active:
        warning = _try_restart_with_warning(manager, cam.id, "start")
        if warning:
            response.worker_warning = warning
    return response


@router.patch("/{camera_id}", response_model=CameraRead)
def update_camera(
    camera_id: int,
    payload: CameraUpdate,
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> CameraRead:
    repo = CameraRepository(db)
    cam = repo.get(camera_id)
    if cam is None:
        raise NotFoundError(f"Camera {camera_id} not found")

    data = payload.model_dump(exclude_unset=True)
    new_name = data.get("name")
    if new_name is not None and new_name != cam.name:
        clash = repo.get_by_name(new_name)
        if clash is not None and clash.id != cam.id:
            raise AlreadyExistsError(f"Camera '{new_name}' already exists")

    repo.update(cam, data)
    db.commit()
    response = CameraRead.model_validate(cam)
    warning = _try_restart_with_warning(manager, camera_id, "restart")
    if warning:
        response.worker_warning = warning
    return response


@router.delete("/{camera_id}", status_code=204, response_model=None)
def delete_camera(
    camera_id: int,
    hard: bool = Query(
        default=True,
        description=(
            "When true (default) the camera row is permanently removed from "
            "the database. When false the row is only deactivated, so the "
            "operator can re-enable it later. Past attendance/snapshot rows "
            "are kept either way because their FK uses ON DELETE SET NULL."
        ),
    ),
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> None:
    """Remove or deactivate a camera.

    Steps:
      1. Stop the worker thread (preview, drain, detection all shut down).
      2. Unregister the camera from the go2rtc WebRTC bridge.
      3. Either DELETE the row (hard=true) or set is_active=False (hard=false).

    Historical attendance + snapshot rows are preserved either way: their
    `camera_id` FK is declared `ON DELETE SET NULL`, so once the camera row
    is gone they keep their data but their camera_id column goes to NULL.
    """
    repo = CameraRepository(db)
    cam = repo.get(camera_id)
    if cam is None:
        raise NotFoundError(f"Camera {camera_id} not found")

    # 1. Stop the live worker first so it doesn't try to read a dead row
    #    or leave a half-closed RTSP socket behind.
    try:
        manager.stop(camera_id)
    except Exception:
        log.warning(
            "Worker stop for camera id=%s raised — continuing with delete",
            camera_id,
            exc_info=True,
        )

    # 2. Unregister from go2rtc so the WebRTC bridge stops trying to keep
    #    the RTSP source open.
    _resync_go2rtc(camera_id, None, removed=True)

    if hard:
        # 3a. Actually delete the row. Cascade is handled by the DB:
        #     attendance_event.camera_id and unknown_face.camera_id both
        #     declare ON DELETE SET NULL, so their rows survive with
        #     camera_id=NULL. No data loss.
        db.delete(cam)
        db.commit()
        log.info("Camera id=%s permanently deleted by admin", camera_id)
    else:
        # 3b. Soft delete — just deactivate.
        cam.is_active = False
        db.commit()
        log.info("Camera id=%s deactivated (soft delete) by admin", camera_id)


@router.post("/{camera_id}/restart", status_code=204, response_model=None)
def restart_camera(
    camera_id: int,
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> None:
    manager.restart(camera_id)


@router.get("/{camera_id}/preview.jpg", response_class=Response)
def camera_preview(
    camera_id: int,
    annotated: bool = Query(True),
    max_age_seconds: float = Query(10.0, ge=0.5, le=120.0),
    quality: int = Query(80, ge=30, le=95),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(get_current_admin),
) -> Response:
    """Return the most recent frame from this camera as a JPEG, with
    face-detection bounding boxes drawn on top by default.
    Used by the `/live` page to render a 4-camera grid in near-real-time.
    """
    payload = manager.get_preview_jpeg(
        camera_id,
        annotated=annotated,
        max_age_seconds=max_age_seconds,
        quality=quality,
    )
    if payload is None:
        raise NotFoundError(f"No recent frame from camera {camera_id}")
    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{camera_id}/preview.mjpeg")
def camera_preview_mjpeg(
    camera_id: int,
    request: Request,
    token: str | None = Query(default=None, description="JWT bearer token (used when the <img> tag can't set Authorization header)"),
    annotated: bool = Query(True),
    quality: int = Query(70, ge=30, le=95),
    max_fps: int = Query(30, ge=1, le=60),
    max_width: int = Query(1280, ge=320, le=3840),
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
) -> StreamingResponse:
    """Push a live MJPEG stream of the camera — multipart/x-mixed-replace.

    The browser displays this via a simple `<img src="...">` tag and
    decodes new frames as they arrive over one persistent HTTP connection.
    Latency is ~80-150 ms total (camera + FFmpeg buffer + JPEG encode +
    TCP send + browser decode), an order of magnitude lower than polling
    `preview.jpg` at 200 ms intervals.

    Auth: `<img>` tags can't set an `Authorization` header, so this
    endpoint accepts the JWT via the `aa_token` cookie OR a `?token=`
    query parameter (frontend supplies the parameter by reading the
    cookie via js-cookie). Both fall back to the same JWT validation.
    """
    # ---- Auth via cookie or query token ----
    bearer: str | None = None
    cookie_token = request.cookies.get("aa_token")
    if cookie_token:
        bearer = cookie_token
    elif token:
        bearer = token
    if not bearer:
        raise AuthenticationError("Missing token (provide ?token= or aa_token cookie)")
    # Re-use the auth service for token validation. Any failure here surfaces
    # as a 401 via the AppError handler in main.py.
    from app.services.auth_service import AuthService
    AuthService(db).resolve_admin(bearer)

    # Generator -> StreamingResponse. Returning a generator without await
    # is fine in FastAPI — the framework iterates it lazily as a stream.
    return StreamingResponse(
        manager.stream_mjpeg(
            camera_id,
            annotated=annotated,
            quality=quality,
            max_fps=max_fps,
            max_width=max_width,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",  # tell Caddy/Nginx not to buffer
            "Connection": "keep-alive",
        },
    )


@router.websocket("/{camera_id}/preview.ws")
async def camera_preview_ws(
    ws: WebSocket,
    camera_id: int,
    token: str | None = Query(default=None),
    annotated: bool = Query(True),
    # Defaults tuned for absolute lowest latency. Quality 60 at 640px
    # produces ~12-20 KB JPEGs that encode in <5 ms on the backend and
    # decode in <8 ms in the browser. Bumping back to 70/854 if needed
    # for sharper face boxes is a per-tile query param.
    quality: int = Query(60, ge=30, le=95),
    max_width: int = Query(640, ge=320, le=3840),
):
    """Backpressure-aware WebSocket live stream.

    The fundamental difference from `/preview.mjpeg`: this endpoint sends
    the next frame only AFTER the previous send has been fully accepted
    by the browser's receive buffer. If the browser slows down (tab
    backgrounded, CPU bound, slow network), the server pauses producing
    frames instead of letting them pile up in the TCP queue. There is
    therefore NO buffer build-up and NO accumulating latency, ever.

    Wire format:
      Each frame is a single binary WebSocket message. The first 4 bytes
      are a uint32 timestamp (ms since worker start) followed by JPEG
      bytes. Frontend can use the timestamp to render a "live lag"
      indicator and drop frames that are too stale to bother decoding.

    Auth: cookie OR ?token= query param (browser WebSocket API can't
    set Authorization headers).
    """
    # Auth — accept cookie or query token. Errors return BEFORE accept()
    # so the browser sees a clean handshake failure.
    cookie_token = ws.cookies.get("aa_token")
    bearer = cookie_token or token
    if not bearer:
        await ws.close(code=4401, reason="Missing token")
        return

    from app.db.session import get_sessionmaker
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        from app.services.auth_service import AuthService
        AuthService(db).resolve_admin(bearer)
    except Exception:
        await ws.close(code=4401, reason="Invalid token")
        return
    finally:
        db.close()

    manager = ws.app.state.camera_manager
    if manager is None:
        await ws.close(code=4503, reason="Camera manager not ready")
        return

    await ws.accept()

    last_frame_at: float = 0.0
    try:
        while True:
            # Grab the worker fresh each iteration so a restart picks up
            # the new instance automatically.
            with manager._lock:  # noqa: SLF001 — sync read of dict
                worker = manager._workers.get(camera_id)  # noqa: SLF001
            if worker is None or not worker.is_running:
                await ws.close(code=4404, reason="Camera not running")
                return

            # FAST PATH: client uses the default params (640 width, q60,
            # annotated=true). The worker's fast thread has already
            # encoded this exact frame. Just await it and send — zero
            # additional copy, zero per-client encode.
            use_shared_encode = (
                annotated
                and quality == worker._PREVIEW_QUALITY  # noqa: SLF001
                and max_width == worker._PREVIEW_MAX_WIDTH  # noqa: SLF001
            )

            if use_shared_encode:
                snapshot = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: worker.wait_next_jpeg(last_frame_at, timeout=1.0),
                )
                if snapshot is None:
                    continue
                jpeg, frame_at = snapshot
                last_frame_at = frame_at
            else:
                # SLOW PATH: client wants non-default size/quality
                # (fullscreen modal, etc). Fall back to per-client
                # annotate + resize + encode.
                snapshot = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: worker.wait_next_preview(last_frame_at, timeout=1.0),
                )
                if snapshot is None:
                    continue
                frame, detections, frame_at = snapshot
                last_frame_at = frame_at

                def _encode():
                    from app.services.preview_service import (
                        annotate_frame,
                        encode_jpeg,
                    )
                    f = frame
                    if annotated and detections:
                        f = annotate_frame(f, detections, in_place=True)
                    if max_width and f.shape[1] > max_width:
                        import cv2 as _cv2
                        h_orig, w_orig = f.shape[:2]
                        scale = max_width / w_orig
                        new_size = (max_width, int(round(h_orig * scale)))
                        f = _cv2.resize(
                            f, new_size, interpolation=_cv2.INTER_NEAREST
                        )
                    return encode_jpeg(f, quality=quality)

                jpeg = await asyncio.get_event_loop().run_in_executor(None, _encode)

            # Backpressure: send_bytes() AWAITS the underlying TCP write
            # to complete (Starlette's WS wraps it as an asyncio coroutine).
            # If the browser hasn't drained the previous frame yet, this
            # coroutine pauses here — naturally pacing us to the browser's
            # consume rate. NO buffer build-up possible.
            #
            # Frame header: 4-byte big-endian uint32 of wall-clock ms
            # (since UNIX epoch, mod 2^32). MUST be wall-clock, not
            # time.monotonic(): the browser compares this against
            # performance.now() to estimate producer→consumer lag, and
            # those domains have no shared origin. `frame_at` is the
            # worker's monotonic capture timestamp, used internally for
            # ordering only — we re-stamp here with wall-clock time so
            # the client's lag computation is meaningful and stable
            # across server restarts. The uint32 wraps every ~49.7 days,
            # but the client only ever uses *deltas* from the first
            # frame's value (see camera-ws-stream.tsx), so wrap is safe.
            wall_ms = int(time.time() * 1000) & 0xFFFFFFFF
            header = wall_ms.to_bytes(4, "big")
            try:
                await ws.send_bytes(header + jpeg)
            except (WebSocketDisconnect, RuntimeError):
                return
    except WebSocketDisconnect:
        return
    except Exception:
        log.exception("WebSocket preview crashed for camera_id=%s", camera_id)
        try:
            await ws.close(code=4500, reason="Server error")
        except Exception:
            pass
        return


@router.get("/{camera_id}/webrtc-info")
def camera_webrtc_info(
    camera_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> dict:
    """Return the URLs the browser needs to open a WebRTC stream via go2rtc.

    Returns 503 if go2rtc isn't running — frontend then falls back to
    the WebSocket JPEG stream automatically.
    """
    go2rtc = get_go2rtc_service()
    if not go2rtc.is_running:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail={
                "error": "go2rtc_unavailable",
                "message": go2rtc.last_error or "WebRTC bridge not running",
                "fallback": "websocket",
            },
        )
    # Make sure the camera exists & is active
    cam = CameraRepository(db).get(camera_id)
    if cam is None or not cam.is_active:
        raise NotFoundError(f"Camera {camera_id} not found or inactive")

    # Tell go2rtc about this camera in case it isn't already configured.
    go2rtc.sync_cameras([(cam.id, cam.rtsp_url)])

    # Resolve the host the browser used to load the page so its ICE
    # candidates resolve correctly. fall back to 127.0.0.1.
    browser_host = (
        request.headers.get("X-Forwarded-Host")
        or request.url.hostname
        or "127.0.0.1"
    )
    info = go2rtc.stream_info_for_browser(camera_id, browser_host=browser_host)
    return {
        "name": info.name,
        "webrtc_url": info.webrtc_url,
        "mse_url": info.mse_url,
        "mjpeg_url": info.mjpeg_url,
    }
