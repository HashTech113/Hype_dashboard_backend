from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.exceptions import (
    FaceRecognitionError,
    FrameUnavailableError,
    NotFoundError,
    ValidationError,
)
from app.core.logger import get_logger
from app.models.face_embedding import EmployeeFaceEmbedding
from app.models.face_image import EmployeeFaceImage
from app.repositories.embedding_repo import EmbeddingRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.face_image_repo import FaceImageRepository
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.services.settings_service import get_settings_service
from app.utils.image_utils import decode_image_bytes, write_jpeg

log = get_logger(__name__)


@dataclass
class TrainingOutcome:
    employee_id: int
    accepted: int
    rejected: int
    total_embeddings: int
    errors: list[str]


class TrainingService:
    _auto_lock = threading.Lock()
    _auto_last: dict[int, float] = {}

    def __init__(
        self,
        db: Session,
        face_service: FaceService,
        embedding_cache: EmbeddingCache,
    ) -> None:
        self.db = db
        self.face_service = face_service
        self.cache = embedding_cache
        self.employee_repo = EmployeeRepository(db)
        self.image_repo = FaceImageRepository(db)
        self.embedding_repo = EmbeddingRepository(db)

    def enroll(
        self,
        employee_id: int,
        images: list[tuple[str, bytes]],
        *,
        admin_id: int | None = None,
        replace: bool = False,
    ) -> TrainingOutcome:
        env = get_settings()
        svc_settings = get_settings_service().get()
        min_imgs = svc_settings.train_min_images
        max_imgs = svc_settings.train_max_images

        employee = self.employee_repo.get(employee_id)
        if employee is None:
            raise NotFoundError(f"Employee {employee_id} not found")
        if not employee.is_active:
            raise ValidationError("Cannot train an inactive employee")

        if not (min_imgs <= len(images) <= max_imgs):
            raise ValidationError(
                f"Provide between {min_imgs} and {max_imgs} images (got {len(images)})"
            )

        if replace:
            self.image_repo.delete_by_employee(employee_id)
            emp_dir = Path(env.TRAINING_DIR) / employee.employee_code
            if emp_dir.exists():
                for p in emp_dir.glob("*"):
                    try:
                        p.unlink()
                    except OSError:
                        pass

        accepted = 0
        rejected = 0
        errors: list[str] = []

        for filename, data in images:
            try:
                img = decode_image_bytes(data)
                if img is None:
                    errors.append(f"{filename}: could not decode image")
                    rejected += 1
                    continue

                file_hash = hashlib.sha256(data).hexdigest()
                if self.image_repo.get_by_hash(employee_id, file_hash) is not None:
                    errors.append(f"{filename}: duplicate image (same hash)")
                    rejected += 1
                    continue

                self._persist_face(
                    employee=employee,
                    frame_bgr=img,
                    admin_id=admin_id,
                    file_hash=file_hash,
                    filename_hint=filename,
                )
                accepted += 1
            except FaceRecognitionError as exc:
                errors.append(f"{filename}: {exc.message}")
                rejected += 1
            except Exception as exc:
                log.exception("Unexpected training error for %s", filename)
                errors.append(f"{filename}: {exc}")
                rejected += 1

        if accepted == 0:
            raise ValidationError(
                "No valid face found in any provided image; " + "; ".join(errors)
            )

        self.db.flush()
        total = self.embedding_repo.count_by_employee(employee.id)
        self.cache.load_from_db()
        log.info(
            "Trained employee_id=%s code=%s accepted=%d rejected=%d total=%d",
            employee.id,
            employee.employee_code,
            accepted,
            rejected,
            total,
        )
        return TrainingOutcome(
            employee_id=employee.id,
            accepted=accepted,
            rejected=rejected,
            total_embeddings=total,
            errors=errors,
        )

    def capture_and_enroll(
        self,
        *,
        employee_id: int,
        frame_bgr: np.ndarray | None,
        admin_id: int | None,
    ) -> TrainingOutcome:
        if frame_bgr is None:
            raise FrameUnavailableError(
                "Camera has no fresh frame available; ensure the camera is running and try again"
            )
        svc_settings = get_settings_service().get()
        max_imgs = svc_settings.train_max_images

        employee = self.employee_repo.get(employee_id)
        if employee is None:
            raise NotFoundError(f"Employee {employee_id} not found")
        if not employee.is_active:
            raise ValidationError("Cannot train an inactive employee")

        current_total = self.embedding_repo.count_by_employee(employee_id)
        if current_total >= max_imgs:
            raise ValidationError(
                f"Employee already has {current_total} embeddings (max {max_imgs})"
            )

        ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise ValidationError("Failed to encode captured frame")
        file_hash = hashlib.sha256(buf.tobytes()).hexdigest()

        accepted = 0
        errors: list[str] = []
        try:
            if self.image_repo.get_by_hash(employee_id, file_hash) is not None:
                errors.append("duplicate frame (same hash already enrolled)")
            else:
                captured_vec = self._persist_face(
                    employee=employee,
                    frame_bgr=frame_bgr,
                    admin_id=admin_id,
                    file_hash=file_hash,
                    filename_hint="live-capture",
                )
                accepted = 1
        except FaceRecognitionError as exc:
            errors.append(exc.message)
        except Exception as exc:
            log.exception("Unexpected live-capture error")
            errors.append(str(exc))

        if accepted == 0:
            raise ValidationError(
                "Live capture did not yield a valid face: " + "; ".join(errors)
            )

        self.db.flush()
        total = self.embedding_repo.count_by_employee(employee.id)
        # H4 fix: incremental append, no full DB reload
        self.cache.append_vectors(
            employee_id=employee.id,
            employee_code=employee.employee_code,
            employee_name=employee.name,
            new_vectors=[captured_vec],
        )
        log.info(
            "Live-captured employee_id=%s code=%s total=%d", employee.id, employee.employee_code, total
        )
        return TrainingOutcome(
            employee_id=employee.id,
            accepted=accepted,
            rejected=0,
            total_embeddings=total,
            errors=errors,
        )

    def auto_enroll_from_frame(
        self,
        *,
        employee_id: int,
        frame_bgr: np.ndarray,
        match_score: float,
    ) -> bool:
        """Auto-add a new embedding after a high-confidence recognition.

        Rate-limited and size-capped. Safe to call from camera worker threads —
        all errors are caught and logged; never raises.
        """
        settings = get_settings_service().get()
        if not settings.auto_update_enabled:
            return False
        if match_score < settings.auto_update_threshold:
            return False

        now = time.monotonic()
        cooldown = float(settings.auto_update_cooldown_seconds)
        with TrainingService._auto_lock:
            last = TrainingService._auto_last.get(employee_id)
            if last is not None and (now - last) < cooldown:
                return False
            TrainingService._auto_last[employee_id] = now

        try:
            employee = self.employee_repo.get(employee_id)
            if employee is None or not employee.is_active:
                return False

            count = self.embedding_repo.count_by_employee(employee_id)
            if count >= settings.train_max_images:
                return False

            ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
            if not ok:
                return False
            file_hash = hashlib.sha256(buf.tobytes()).hexdigest()
            if self.image_repo.get_by_hash(employee_id, file_hash) is not None:
                return False

            vec = self._persist_face(
                employee=employee,
                frame_bgr=frame_bgr,
                admin_id=None,
                file_hash=file_hash,
                filename_hint="auto",
            )
            self.db.flush()
            # H4 fix: incremental append, NOT a full DB reload. Previously
            # this triggered a full SELECT of every embedding vector on the
            # camera worker thread — stalling RTSP reads for hundreds of ms
            # after every auto-enrollment.
            self.cache.append_vectors(
                employee_id=employee.id,
                employee_code=employee.employee_code,
                employee_name=employee.name,
                new_vectors=[vec],
            )
            log.info(
                "Auto-enrolled emp_id=%s code=%s match=%.3f new_total=%d",
                employee_id,
                employee.employee_code,
                match_score,
                count + 1,
            )
            return True
        except Exception:
            log.exception("Auto-enroll failed for emp_id=%s", employee_id)
            with TrainingService._auto_lock:
                TrainingService._auto_last.pop(employee_id, None)
            return False

    def rebuild_cache(self) -> None:
        self.cache.load_from_db()

    def delete_image(self, image_id: int) -> None:
        img = self.image_repo.get(image_id)
        if img is None:
            raise NotFoundError(f"Face image {image_id} not found")
        path = Path(img.file_path)
        self.image_repo.delete(img)
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            log.warning("Failed to remove training image %s: %s", path, exc)
        self.db.flush()
        self.cache.load_from_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _persist_face(
        self,
        *,
        employee,
        frame_bgr: np.ndarray,
        admin_id: int | None,
        file_hash: str,
        filename_hint: str,
    ) -> np.ndarray:
        """Detect, persist, return the L2-normalized embedding.

        Returns the vector so callers can pass it to
        EmbeddingCache.append_vectors() and skip the full DB reload — see
        auto_enroll_from_frame and capture_and_enroll (H4 fix).
        """
        env = get_settings()
        face = self.face_service.detect_single(frame_bgr)
        vec = face.embedding.astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            raise FaceRecognitionError("Zero-norm embedding")
        vec = vec / norm

        prefix = "auto" if filename_hint == "auto" else "img"
        out_path = (
            Path(env.TRAINING_DIR)
            / employee.employee_code
            / f"{prefix}_{uuid.uuid4().hex}.jpg"
        )
        write_jpeg(out_path, frame_bgr, quality=92)

        h, w = frame_bgr.shape[:2]
        image_row = EmployeeFaceImage(
            employee_id=employee.id,
            file_path=str(out_path),
            file_hash=file_hash,
            width=int(w),
            height=int(h),
            uploaded_by=admin_id,
        )
        self.image_repo.add(image_row)

        emb = EmployeeFaceEmbedding(
            employee_id=employee.id,
            image_id=image_row.id,
            vector=EmbeddingCache.pack(vec),
            dim=int(vec.size),
            model_name=env.FACE_MODEL_NAME,
            quality_score=face.det_score,
        )
        self.embedding_repo.add(emb)
        return vec
