from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import UnknownCaptureStatus, UnknownClusterStatus
from app.schemas.common import ORMModel


# ----------------------------------------------------------------------
# Cluster reads
# ----------------------------------------------------------------------


class UnknownCaptureRead(ORMModel):
    id: int
    cluster_id: int
    file_path: str
    camera_id: int | None
    camera_name: str | None = None
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    det_score: float
    sharpness_score: float
    captured_at: datetime
    status: UnknownCaptureStatus
    created_at: datetime


class UnknownClusterRead(ORMModel):
    """Summary row used in the cluster grid. `representative_capture_id`
    points at the highest-quality KEEP capture so the frontend can render
    a single thumbnail without loading the whole capture list.
    """

    id: int
    label: str | None
    status: UnknownClusterStatus
    member_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    promoted_employee_id: int | None
    merged_into_cluster_id: int | None
    representative_capture_id: int | None = None
    created_at: datetime
    updated_at: datetime


class UnknownClusterDetail(UnknownClusterRead):
    """Full cluster view: summary + every capture (KEEP + DISCARDED)."""

    captures: list[UnknownCaptureRead]


# ----------------------------------------------------------------------
# Mutations
# ----------------------------------------------------------------------


class UnknownClusterUpdate(BaseModel):
    """Patch: set/clear the admin-assigned label without promoting."""

    label: str | None = Field(default=None, max_length=128)


class PromoteToNewRequest(BaseModel):
    """Body for `POST /unknowns/clusters/{id}/promote/new` —
    create a fresh Employee and train it with the cluster's captures.
    """

    employee_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    designation: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, max_length=128)
    join_date: date | None = None
    is_active: bool = True


class PromoteResponse(BaseModel):
    cluster_id: int
    employee_id: int
    employee_code: str
    employee_name: str
    cluster_was_new_employee: bool
    captures_promoted: int  # how many became EmployeeFaceEmbedding rows
    captures_skipped: int  # duplicates / missing files / over cap
    total_employee_embeddings: int  # final count after this promotion


# ----------------------------------------------------------------------
# Re-cluster + purge admin operations
# ----------------------------------------------------------------------


class ReclusterRequest(BaseModel):
    min_cluster_size: int = Field(default=2, ge=2, le=20)
    min_samples: int = Field(default=1, ge=1, le=20)


class ReclusterResponse(BaseModel):
    ran: bool
    reason: str
    captures_total: int
    clusters_before: int
    clusters_after_pending: int
    clusters_merged: int
    captures_migrated: int
    noise_count: int
    duration_ms: int


class PurgeRequest(BaseModel):
    """Time-based + status-based retention sweep.

    `max_age_days=null` falls back to the runtime setting
    `unknown_retention_days`. By default only IGNORED + MERGED clusters
    are purged; pass `include_promoted=True` to also reclaim disk for
    clusters whose captures were already migrated to the employee
    training folder.
    """

    max_age_days: int | None = Field(default=None, ge=1, le=3650)
    include_promoted: bool = False


class PurgeResponse(BaseModel):
    cutoff: datetime
    clusters_examined: int
    clusters_deleted: int
    captures_deleted: int
    files_deleted: int
    bytes_freed: int
