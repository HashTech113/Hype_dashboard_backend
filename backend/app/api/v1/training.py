from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import (
    get_camera_manager,
    get_db,
    get_embedding_cache,
    get_face_service,
    require_roles,
)
from app.core.constants import Role
from app.core.exceptions import NotFoundError, ValidationError
from app.models.admin import Admin
from app.repositories.embedding_repo import EmbeddingRepository
from app.repositories.face_image_repo import FaceImageRepository
from app.schemas.training import EmbeddingRead, FaceImageRead, TrainingResult
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.services.settings_service import get_settings_service
from app.services.training_service import TrainingService
from app.workers.camera_manager import CameraManager

router = APIRouter(prefix="/employees/{employee_id}/training", tags=["training"])


@router.get("/images", response_model=list[FaceImageRead])
def list_images(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.VIEWER)),
) -> list[FaceImageRead]:
    items = FaceImageRepository(db).list_by_employee(employee_id)
    return [FaceImageRead.model_validate(i) for i in items]


@router.get("/embeddings", response_model=list[EmbeddingRead])
def list_embeddings(
    employee_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN, Role.VIEWER)),
) -> list[EmbeddingRead]:
    items = EmbeddingRepository(db).list_by_employee(employee_id)
    return [EmbeddingRead.model_validate(i) for i in items]


@router.post("/images", response_model=TrainingResult)
async def upload_training_images(
    employee_id: int,
    replace: bool = False,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    face_service: FaceService = Depends(get_face_service),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> TrainingResult:
    max_imgs = get_settings_service().get().train_max_images
    if not files:
        raise ValidationError("No files uploaded")
    if len(files) > max_imgs:
        raise ValidationError(f"Too many files: max {max_imgs}")
    images: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        images.append((f.filename or "image.jpg", content))

    outcome = TrainingService(db, face_service, cache).enroll(
        employee_id, images, admin_id=admin.id, replace=replace
    )
    return TrainingResult(
        employee_id=outcome.employee_id,
        accepted=outcome.accepted,
        rejected=outcome.rejected,
        total_embeddings=outcome.total_embeddings,
        errors=outcome.errors,
    )


@router.post("/capture", response_model=TrainingResult)
def capture_from_camera(
    employee_id: int,
    camera_id: int,
    max_age_seconds: float = 5.0,
    db: Session = Depends(get_db),
    face_service: FaceService = Depends(get_face_service),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    manager: CameraManager = Depends(get_camera_manager),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> TrainingResult:
    frame = manager.get_latest_frame(camera_id, max_age_seconds=max_age_seconds)
    outcome = TrainingService(db, face_service, cache).capture_and_enroll(
        employee_id=employee_id,
        frame_bgr=frame,
        admin_id=admin.id,
    )
    return TrainingResult(
        employee_id=outcome.employee_id,
        accepted=outcome.accepted,
        rejected=outcome.rejected,
        total_embeddings=outcome.total_embeddings,
        errors=outcome.errors,
    )


@router.post("/rebuild-cache", status_code=204, response_model=None)
def rebuild_cache(
    employee_id: int,
    db: Session = Depends(get_db),
    face_service: FaceService = Depends(get_face_service),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> None:
    TrainingService(db, face_service, cache).rebuild_cache()


@router.delete("/images/{image_id}", status_code=204, response_model=None)
def delete_image(
    employee_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    face_service: FaceService = Depends(get_face_service),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> None:
    img = FaceImageRepository(db).get(image_id)
    if img is None or img.employee_id != employee_id:
        raise NotFoundError(
            f"Face image {image_id} not found for employee {employee_id}"
        )
    TrainingService(db, face_service, cache).delete_image(image_id)
