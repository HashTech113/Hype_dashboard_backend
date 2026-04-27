"""Retention purge for unknown-face clusters and their captures.

By default this hard-deletes IGNORED + MERGED clusters whose
`last_seen_at` is older than `unknown_retention_days` (admin-tunable,
default 30). PROMOTED clusters are kept by default — their captures
were already copied into the employee's training folder, but the
originals provide audit trail. Pass `include_promoted=True` to also
reclaim disk for those.

Always preserves PENDING clusters — those are still in the admin's
review queue and must never be auto-deleted.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import UnknownClusterStatus
from app.core.logger import get_logger
from app.repositories.unknown_capture_repo import UnknownCaptureRepository
from app.repositories.unknown_cluster_repo import UnknownClusterRepository
from app.services.settings_service import get_settings_service
from app.services.unknown_capture_service import UnknownCaptureService
from app.utils.time_utils import now_utc

log = get_logger(__name__)


@dataclass(frozen=True)
class PurgeOutcome:
    cutoff: datetime
    clusters_examined: int
    clusters_deleted: int
    captures_deleted: int
    files_deleted: int
    bytes_freed: int


class UnknownPurgeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.cluster_repo = UnknownClusterRepository(db)
        self.capture_repo = UnknownCaptureRepository(db)

    def purge(
        self,
        *,
        max_age_days: int | None = None,
        include_promoted: bool = False,
    ) -> PurgeOutcome:
        settings = get_settings_service().get()
        days = int(max_age_days) if max_age_days is not None else int(
            settings.unknown_retention_days
        )
        cutoff = now_utc() - timedelta(days=days)

        statuses: list[UnknownClusterStatus] = [
            UnknownClusterStatus.IGNORED,
            UnknownClusterStatus.MERGED,
        ]
        if include_promoted:
            statuses.append(UnknownClusterStatus.PROMOTED)

        candidates = self.cluster_repo.list_for_purge(
            statuses=statuses, max_last_seen=cutoff
        )

        clusters_deleted = 0
        captures_deleted = 0
        files_deleted = 0
        bytes_freed = 0

        unknowns_root = Path(get_settings().UNKNOWNS_DIR)

        for cluster in candidates:
            captures = self.capture_repo.list_all_for_cluster(cluster.id)
            for cap in captures:
                p = Path(cap.file_path)
                if p.exists():
                    try:
                        size = p.stat().st_size
                        p.unlink()
                        files_deleted += 1
                        bytes_freed += size
                    except OSError as exc:
                        log.warning(
                            "Failed to remove capture file %s: %s", p, exc
                        )
                self.db.delete(cap)
                captures_deleted += 1

            cluster_dir = unknowns_root / f"cluster_{cluster.id}"
            if cluster_dir.exists():
                try:
                    shutil.rmtree(cluster_dir, ignore_errors=True)
                except OSError as exc:
                    log.warning(
                        "Failed to remove cluster dir %s: %s", cluster_dir, exc
                    )

            UnknownCaptureService.reset_cooldown(cluster.id)
            self.db.delete(cluster)
            clusters_deleted += 1

        self.db.flush()
        log.info(
            "Unknowns purge: cutoff=%s examined=%d clusters=%d captures=%d files=%d bytes=%d",
            cutoff.isoformat(),
            len(candidates),
            clusters_deleted,
            captures_deleted,
            files_deleted,
            bytes_freed,
        )
        return PurgeOutcome(
            cutoff=cutoff,
            clusters_examined=len(candidates),
            clusters_deleted=clusters_deleted,
            captures_deleted=captures_deleted,
            files_deleted=files_deleted,
            bytes_freed=bytes_freed,
        )
