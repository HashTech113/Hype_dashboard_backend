from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import (
    get_camera_manager,
    get_current_admin,
    get_db,
    require_roles,
)
from app.core.constants import Role
from app.core.exceptions import AlreadyExistsError, NotFoundError
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
)
from app.workers.camera_manager import CameraManager
from app.workers.rtsp_probe import probe_rtsp

router = APIRouter(prefix="/cameras", tags=["cameras"])
log = get_logger(__name__)


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
                processed_frames=int(s["processed_frames"]) if s else 0,
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
    )
    repo.add(cam)
    db.commit()
    response = CameraRead.model_validate(cam)
    if cam.is_active:
        try:
            manager.restart(cam.id)
        except Exception:
            log.exception("Failed to start worker for new camera id=%s", cam.id)
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
    try:
        manager.restart(camera_id)
    except Exception:
        log.exception("Failed to restart worker after camera update id=%s", camera_id)
    return response


@router.delete("/{camera_id}", status_code=204, response_model=None)
def delete_camera(
    camera_id: int,
    db: Session = Depends(get_db),
    manager: CameraManager = Depends(get_camera_manager),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> None:
    repo = CameraRepository(db)
    cam = repo.get(camera_id)
    if cam is None:
        raise NotFoundError(f"Camera {camera_id} not found")
    cam.is_active = False
    db.commit()
    try:
        manager.restart(camera_id)
    except Exception:
        log.exception("Failed to stop worker on delete id=%s", camera_id)


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
