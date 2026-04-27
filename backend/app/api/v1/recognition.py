from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_current_admin, get_embedding_cache, get_face_service
from app.config import get_settings
from app.core.exceptions import ValidationError
from app.models.admin import Admin
from app.schemas.recognition import CacheStats, IdentifyResult
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.services.recognition_service import RecognitionService
from app.services.settings_service import get_settings_service
from app.utils.image_utils import decode_image_bytes

router = APIRouter(prefix="/recognition", tags=["recognition"])


@router.get("/cache/stats", response_model=CacheStats)
def cache_stats(
    cache: EmbeddingCache = Depends(get_embedding_cache),
    _: Admin = Depends(get_current_admin),
) -> CacheStats:
    settings = get_settings_service().get()
    return CacheStats(
        employee_count=cache.employee_count(),
        total_vectors=cache.size(),
        model_name=get_settings().FACE_MODEL_NAME,
        threshold=settings.face_match_threshold,
    )


@router.post("/cache/reload", status_code=204, response_model=None)
def reload_cache(
    cache: EmbeddingCache = Depends(get_embedding_cache),
    _: Admin = Depends(get_current_admin),
) -> None:
    cache.load_from_db()


@router.post("/identify", response_model=IdentifyResult)
async def identify(
    file: UploadFile = File(...),
    face_service: FaceService = Depends(get_face_service),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    _: Admin = Depends(get_current_admin),
) -> IdentifyResult:
    data = await file.read()
    img = decode_image_bytes(data)
    if img is None:
        raise ValidationError("Could not decode image")

    face = face_service.detect_single(img)
    settings = get_settings_service().get()
    match = RecognitionService(cache).match(face.embedding)

    employee_code = None
    employee_name = None
    if match.employee_id is not None:
        _, _, entries = cache.snapshot()
        for e in entries:
            if e.employee_id == match.employee_id:
                employee_code = e.employee_code
                employee_name = e.employee_name
                break

    return IdentifyResult(
        matched=match.employee_id is not None,
        employee_id=match.employee_id,
        employee_code=employee_code,
        employee_name=employee_name,
        score=match.score,
        second_best_score=match.second_best_score,
        threshold=settings.face_match_threshold,
        face_quality=face.det_score,
    )
