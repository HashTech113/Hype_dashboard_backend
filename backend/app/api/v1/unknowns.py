from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_admin,
    get_db,
    get_embedding_cache,
    require_roles,
)
from app.core.constants import Role, UnknownClusterStatus
from app.core.exceptions import InvalidStateError, NotFoundError
from app.core.logger import get_logger
from app.models.admin import Admin
from app.repositories.unknown_capture_repo import UnknownCaptureRepository
from app.repositories.unknown_cluster_repo import UnknownClusterRepository
from app.schemas.common import Page
from app.schemas.unknowns import (
    PromoteResponse,
    PromoteToNewRequest,
    PurgeRequest,
    PurgeResponse,
    ReclusterRequest,
    ReclusterResponse,
    UnknownCaptureRead,
    UnknownClusterDetail,
    UnknownClusterRead,
    UnknownClusterUpdate,
)
from app.services.embedding_cache import EmbeddingCache
from app.services.unknown_capture_service import UnknownCaptureService
from app.services.unknown_promotion_service import UnknownPromotionService
from app.services.unknown_purge_service import UnknownPurgeService
from app.services.unknown_recluster_service import UnknownReclusterService

router = APIRouter(prefix="/unknowns", tags=["unknowns"])
log = get_logger(__name__)


# ----------------------------------------------------------------------
# Listing + detail
# ----------------------------------------------------------------------


@router.get("/clusters", response_model=Page[UnknownClusterRead])
def list_clusters(
    status: UnknownClusterStatus | None = None,
    label: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> Page[UnknownClusterRead]:
    repo = UnknownClusterRepository(db)
    items, total = repo.search(
        status=status, label_query=label, limit=limit, offset=offset
    )
    rep_ids = repo.representative_capture_ids([c.id for c in items])
    rows: list[UnknownClusterRead] = []
    for c in items:
        row = UnknownClusterRead.model_validate(c)
        rows.append(
            row.model_copy(update={"representative_capture_id": rep_ids.get(c.id)})
        )
    return Page[UnknownClusterRead](
        items=rows, total=total, limit=limit, offset=offset
    )


@router.get("/clusters/{cluster_id}", response_model=UnknownClusterDetail)
def get_cluster(
    cluster_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> UnknownClusterDetail:
    cluster = UnknownClusterRepository(db).get(cluster_id)
    if cluster is None:
        raise NotFoundError(f"Unknown cluster {cluster_id} not found")
    captures = UnknownCaptureRepository(db).list_all_for_cluster(cluster_id)

    capture_reads: list[UnknownCaptureRead] = []
    for cap in captures:
        cam_name = cap.camera.name if cap.camera else None
        cr = UnknownCaptureRead.model_validate(cap)
        capture_reads.append(cr.model_copy(update={"camera_name": cam_name}))

    rep_ids = UnknownClusterRepository(db).representative_capture_ids([cluster.id])
    base = UnknownClusterRead.model_validate(cluster).model_copy(
        update={"representative_capture_id": rep_ids.get(cluster.id)}
    )
    return UnknownClusterDetail(**base.model_dump(), captures=capture_reads)


@router.get("/captures/{capture_id}/image")
def get_capture_image(
    capture_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(get_current_admin),
) -> FileResponse:
    capture = UnknownCaptureRepository(db).get(capture_id)
    if capture is None:
        raise NotFoundError(f"Unknown capture {capture_id} not found")
    path = Path(capture.file_path)
    if not path.exists():
        raise NotFoundError(f"Capture file missing on disk: {path}")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)


# ----------------------------------------------------------------------
# Edit (label without promoting)
# ----------------------------------------------------------------------


@router.patch("/clusters/{cluster_id}", response_model=UnknownClusterRead)
def update_cluster(
    cluster_id: int,
    payload: UnknownClusterUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> UnknownClusterRead:
    repo = UnknownClusterRepository(db)
    cluster = repo.get(cluster_id)
    if cluster is None:
        raise NotFoundError(f"Unknown cluster {cluster_id} not found")
    if cluster.status != UnknownClusterStatus.PENDING:
        raise InvalidStateError(
            f"Cannot edit cluster in status {cluster.status.value}"
        )
    data = payload.model_dump(exclude_unset=True)
    if "label" in data:
        cluster.label = data["label"]
    db.flush()
    rep = repo.representative_capture_ids([cluster_id]).get(cluster_id)
    return UnknownClusterRead.model_validate(cluster).model_copy(
        update={"representative_capture_id": rep}
    )


# ----------------------------------------------------------------------
# Promote (the headline feature)
# ----------------------------------------------------------------------


@router.post(
    "/clusters/{cluster_id}/promote/new",
    response_model=PromoteResponse,
    status_code=201,
)
def promote_to_new_employee(
    cluster_id: int,
    payload: PromoteToNewRequest,
    db: Session = Depends(get_db),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> PromoteResponse:
    """Create a new Employee from this cluster and train them with the
    cluster's quality-ranked face captures (up to `train_max_images`).

    Reuses each capture's stored embedding verbatim — no re-detection.
    On success, the recognition cache is hot-reloaded so the next frame
    of this person is recognized as the new employee.
    """
    outcome = UnknownPromotionService(db, cache).promote_to_new_employee(
        cluster_id=cluster_id,
        employee_data=payload.model_dump(),
        admin=admin,
    )
    return PromoteResponse(**outcome.__dict__)


@router.post(
    "/clusters/{cluster_id}/promote/existing/{employee_id}",
    response_model=PromoteResponse,
)
def promote_to_existing_employee(
    cluster_id: int,
    employee_id: int,
    db: Session = Depends(get_db),
    cache: EmbeddingCache = Depends(get_embedding_cache),
    admin: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> PromoteResponse:
    """Append this cluster's captures as additional training images for an
    existing Employee (e.g. their appearance changed and the recognizer
    started missing them). Same accuracy guarantees as `/promote/new`.
    """
    outcome = UnknownPromotionService(db, cache).promote_to_existing_employee(
        cluster_id=cluster_id,
        employee_id=employee_id,
        admin=admin,
    )
    return PromoteResponse(**outcome.__dict__)


# ----------------------------------------------------------------------
# Discard (soft) and admin operations
# ----------------------------------------------------------------------


@router.delete("/clusters/{cluster_id}", status_code=204, response_model=None)
def discard_cluster(
    cluster_id: int,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> None:
    """Mark a cluster IGNORED. Files stay on disk until the next purge."""
    repo = UnknownClusterRepository(db)
    cluster = repo.get(cluster_id)
    if cluster is None:
        raise NotFoundError(f"Unknown cluster {cluster_id} not found")
    if cluster.status not in (
        UnknownClusterStatus.PENDING,
        UnknownClusterStatus.MERGED,
    ):
        raise InvalidStateError(
            f"Cannot discard cluster in status {cluster.status.value}"
        )
    cluster.status = UnknownClusterStatus.IGNORED
    db.flush()
    UnknownCaptureService.reset_cooldown(cluster_id)


@router.post("/recluster", response_model=ReclusterResponse)
def recluster(
    payload: ReclusterRequest | None = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
) -> ReclusterResponse:
    """Re-run HDBSCAN globally over all PENDING captures and reconcile
    drift (merge over-split clusters, leave noise in place).
    """
    p = payload or ReclusterRequest()
    outcome = UnknownReclusterService(db).run(
        min_cluster_size=p.min_cluster_size,
        min_samples=p.min_samples,
    )
    return ReclusterResponse(
        ran=outcome.ran,
        reason=outcome.reason,
        captures_total=outcome.captures_total,
        clusters_before=outcome.clusters_before,
        clusters_after_pending=outcome.clusters_after_pending,
        clusters_merged=outcome.clusters_merged,
        captures_migrated=outcome.captures_migrated,
        noise_count=outcome.noise_count,
        duration_ms=outcome.duration_ms,
    )


@router.post("/purge", response_model=PurgeResponse)
def purge(
    payload: PurgeRequest | None = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(require_roles(Role.SUPER_ADMIN)),
) -> PurgeResponse:
    """Hard-delete IGNORED + MERGED clusters older than the cutoff (and
    their files on disk). Pass `include_promoted=true` to also reclaim
    PROMOTED clusters whose captures already live as employee training
    images. PENDING clusters are never touched.
    """
    p = payload or PurgeRequest()
    outcome = UnknownPurgeService(db).purge(
        max_age_days=p.max_age_days,
        include_promoted=p.include_promoted,
    )
    return PurgeResponse(
        cutoff=outcome.cutoff,
        clusters_examined=outcome.clusters_examined,
        clusters_deleted=outcome.clusters_deleted,
        captures_deleted=outcome.captures_deleted,
        files_deleted=outcome.files_deleted,
        bytes_freed=outcome.bytes_freed,
    )
