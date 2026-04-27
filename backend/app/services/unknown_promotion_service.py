"""Promote an unknown-face cluster to an Employee.

The headline UX: admin reviews a cluster of "this is one unique person",
clicks "Add as Employee", and the system enrols every quality-ranked
capture as a training image for the new (or existing) employee — using
the **stored capture-time embedding** verbatim, never re-running face
detection on the saved JPG crop.

Why reuse the stored embedding?

  * It was computed by the InsightFace `buffalo_l` pipeline against the
    full-resolution camera frame at capture time, with the same model
    and settings the recognition pipeline uses every tick.
  * Re-running detection on a cropped, JPEG-compressed sub-image
    introduces a small but measurable accuracy drop — both because the
    crop loses surrounding context the detector uses, and because JPEG
    quantization perturbs the pixel values the embedder sees.
  * The cluster *was already formed* by these embeddings — promoting
    them as-is preserves whatever similarity structure brought the
    captures together.

Dedup guarantees:

  * `EmployeeFaceImage.file_hash` is a sha256 of the JPG bytes; if the
    admin later uploads the same file via the regular training UI, it
    won't be re-enrolled.
  * Captures over `train_max_images` are skipped (not failed) — the
    quality-ranked ordering means the best are kept.

Cache + cooldown invariants on success:

  * `EmbeddingCache.load_from_db()` is invoked so the next camera frame
    of this person matches the new employee, not the (now stale)
    cluster centroid.
  * The cluster's per-cluster cooldown timestamp is dropped so its
    cluster_id slot is reclaimed.
"""
from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import UnknownClusterStatus
from app.core.exceptions import (
    AlreadyExistsError,
    InvalidStateError,
    NotFoundError,
    ValidationError,
)
from app.core.logger import get_logger
from app.models.admin import Admin
from app.models.employee import Employee
from app.models.face_embedding import EmployeeFaceEmbedding
from app.models.face_image import EmployeeFaceImage
from app.repositories.embedding_repo import EmbeddingRepository
from app.repositories.employee_repo import EmployeeRepository
from app.repositories.face_image_repo import FaceImageRepository
from app.repositories.unknown_capture_repo import UnknownCaptureRepository
from app.repositories.unknown_cluster_repo import UnknownClusterRepository
from app.services.embedding_cache import EmbeddingCache
from app.services.settings_service import get_settings_service
from app.services.unknown_capture_service import UnknownCaptureService

log = get_logger(__name__)


@dataclass(frozen=True)
class PromoteOutcome:
    cluster_id: int
    employee_id: int
    employee_code: str
    employee_name: str
    cluster_was_new_employee: bool
    captures_promoted: int
    captures_skipped: int
    total_employee_embeddings: int


class UnknownPromotionService:
    def __init__(self, db: Session, embedding_cache: EmbeddingCache) -> None:
        self.db = db
        self.cache = embedding_cache
        self.cluster_repo = UnknownClusterRepository(db)
        self.capture_repo = UnknownCaptureRepository(db)
        self.employee_repo = EmployeeRepository(db)
        self.image_repo = FaceImageRepository(db)
        self.embedding_repo = EmbeddingRepository(db)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def promote_to_new_employee(
        self,
        *,
        cluster_id: int,
        employee_data: dict,
        admin: Admin,
    ) -> PromoteOutcome:
        cluster = self._load_promotable(cluster_id)

        code = employee_data["employee_code"]
        if self.employee_repo.get_by_code(code) is not None:
            raise AlreadyExistsError(f"employee_code '{code}' already exists")

        employee = Employee(
            employee_code=code,
            name=employee_data["name"],
            email=employee_data.get("email"),
            phone=employee_data.get("phone"),
            designation=employee_data.get("designation"),
            department=employee_data.get("department"),
            join_date=employee_data.get("join_date"),
            is_active=employee_data.get("is_active", True),
        )
        self.employee_repo.add(employee)

        promoted, skipped = self._migrate_captures(
            cluster_id=cluster.id,
            employee=employee,
            admin_id=admin.id,
        )
        self._finalize_cluster(cluster, employee_id=employee.id)
        total = self.embedding_repo.count_by_employee(employee.id)
        log.info(
            "Promoted cluster_id=%s to NEW employee_id=%s code=%s captures=%d skipped=%d",
            cluster.id,
            employee.id,
            employee.employee_code,
            promoted,
            skipped,
        )
        return PromoteOutcome(
            cluster_id=cluster.id,
            employee_id=employee.id,
            employee_code=employee.employee_code,
            employee_name=employee.name,
            cluster_was_new_employee=True,
            captures_promoted=promoted,
            captures_skipped=skipped,
            total_employee_embeddings=total,
        )

    def promote_to_existing_employee(
        self,
        *,
        cluster_id: int,
        employee_id: int,
        admin: Admin,
    ) -> PromoteOutcome:
        cluster = self._load_promotable(cluster_id)
        employee = self.employee_repo.get(employee_id)
        if employee is None:
            raise NotFoundError(f"Employee {employee_id} not found")
        if not employee.is_active:
            raise ValidationError("Cannot promote into an inactive employee")

        promoted, skipped = self._migrate_captures(
            cluster_id=cluster.id,
            employee=employee,
            admin_id=admin.id,
        )
        if promoted == 0:
            # Nothing was added — most likely employee already at cap or all
            # captures were duplicates. Don't mark cluster PROMOTED in that
            # case; let the admin decide what to do (split, discard, etc.).
            raise ValidationError(
                f"No captures could be added to employee {employee.employee_code}: "
                f"{skipped} skipped (duplicates, missing files, or over cap)"
            )

        self._finalize_cluster(cluster, employee_id=employee.id)
        total = self.embedding_repo.count_by_employee(employee.id)
        log.info(
            "Promoted cluster_id=%s into EXISTING employee_id=%s code=%s captures=%d skipped=%d",
            cluster.id,
            employee.id,
            employee.employee_code,
            promoted,
            skipped,
        )
        return PromoteOutcome(
            cluster_id=cluster.id,
            employee_id=employee.id,
            employee_code=employee.employee_code,
            employee_name=employee.name,
            cluster_was_new_employee=False,
            captures_promoted=promoted,
            captures_skipped=skipped,
            total_employee_embeddings=total,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_promotable(self, cluster_id: int):  # type: ignore[no-untyped-def]
        cluster = self.cluster_repo.get(cluster_id)
        if cluster is None:
            raise NotFoundError(f"Unknown cluster {cluster_id} not found")
        if cluster.status != UnknownClusterStatus.PENDING:
            raise InvalidStateError(
                f"Cluster {cluster_id} is {cluster.status.value}, not PENDING — "
                f"only PENDING clusters can be promoted"
            )
        return cluster

    def _migrate_captures(
        self,
        *,
        cluster_id: int,
        employee: Employee,
        admin_id: int | None,
    ) -> tuple[int, int]:
        """Quality-ranked capture migration.

        Copies up to (`train_max_images` - existing_count) of the cluster's
        KEEP captures into the employee's training folder, writing
        `EmployeeFaceImage` + `EmployeeFaceEmbedding` rows. Reuses each
        capture's stored embedding verbatim — no re-detection.

        Returns `(promoted, skipped)`. Skipped reasons: file missing on
        disk, hash collides with an existing employee image, or the
        per-employee max-images cap was reached mid-loop.
        """
        env = get_settings()
        settings = get_settings_service().get()
        max_imgs = int(settings.train_max_images)

        existing = self.embedding_repo.count_by_employee(employee.id)
        slots_left = max(0, max_imgs - existing)
        if slots_left == 0:
            log.warning(
                "Employee id=%s already at train_max_images=%d; promotion will skip every capture",
                employee.id,
                max_imgs,
            )

        captures = self.capture_repo.list_keep_quality_ranked(cluster_id)
        if not captures:
            return 0, 0

        promoted = 0
        skipped = 0
        training_dir = Path(env.TRAINING_DIR) / employee.employee_code
        training_dir.mkdir(parents=True, exist_ok=True)

        for cap in captures:
            if promoted >= slots_left:
                # Remaining captures intentionally not migrated; record as skipped
                skipped += len(captures) - (promoted + skipped)
                break

            src = Path(cap.file_path)
            if not src.exists():
                log.warning(
                    "Capture id=%s file missing at %s; skipping during promotion",
                    cap.id,
                    src,
                )
                skipped += 1
                continue

            try:
                data = src.read_bytes()
            except OSError as exc:
                log.warning("Capture id=%s read failed: %s", cap.id, exc)
                skipped += 1
                continue

            file_hash = hashlib.sha256(data).hexdigest()
            if (
                self.image_repo.get_by_hash(employee.id, file_hash) is not None
            ):
                log.debug(
                    "Capture id=%s hash matches existing employee image; skipping",
                    cap.id,
                )
                skipped += 1
                continue

            # Decode for width/height; doesn't affect embedding (we reuse
            # the stored capture-time vector below).
            img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                skipped += 1
                continue
            h, w = img.shape[:2]

            dest = training_dir / f"unk_{uuid.uuid4().hex}.jpg"
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                log.warning(
                    "Capture id=%s copy to %s failed: %s; skipping",
                    cap.id,
                    dest,
                    exc,
                )
                skipped += 1
                continue

            image_row = EmployeeFaceImage(
                employee_id=employee.id,
                file_path=str(dest),
                file_hash=file_hash,
                width=int(w),
                height=int(h),
                uploaded_by=admin_id,
            )
            self.image_repo.add(image_row)

            emb_row = EmployeeFaceEmbedding(
                employee_id=employee.id,
                image_id=image_row.id,
                vector=cap.embedding,  # reuse stored bytes verbatim
                dim=int(cap.embedding_dim),
                model_name=cap.model_name,
                quality_score=float(cap.det_score),
            )
            self.embedding_repo.add(emb_row)
            promoted += 1

        self.db.flush()
        return promoted, skipped

    def _finalize_cluster(self, cluster, *, employee_id: int) -> None:  # type: ignore[no-untyped-def]
        cluster.status = UnknownClusterStatus.PROMOTED
        cluster.promoted_employee_id = employee_id
        self.db.flush()
        # Hot-reload the recognition cache so the next frame of this
        # person matches the new employee instead of the (now-stale)
        # cluster centroid. Bounded I/O — cache is small.
        self.cache.load_from_db()
        # Free the in-process cooldown slot for this cluster_id.
        UnknownCaptureService.reset_cooldown(cluster.id)
