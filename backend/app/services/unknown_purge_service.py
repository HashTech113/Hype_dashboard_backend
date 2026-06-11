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
        """Two-phase purge (H7 fix).

        Phase 1: collect file paths + delete DB rows + commit.  Short
        transaction holds row locks only briefly, so concurrent camera
        worker inserts of new captures aren't blocked while we walk
        thousands of files on Windows.

        Phase 2: unlink files + rmtree directories AFTER the commit. File
        IO no longer happens inside the open transaction; a slow AV scan
        on the unlink side cannot drain the DB connection pool.
        """
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

        unknowns_root = Path(get_settings().UNKNOWNS_DIR)
        files_to_unlink: list[str] = []
        dirs_to_remove: list[Path] = []
        captures_deleted = 0
        clusters_deleted = 0

        # ----- Phase 1: DB-only deletes (short transaction) -----
        for cluster in candidates:
            captures = self.capture_repo.list_all_for_cluster(cluster.id)
            for cap in captures:
                if cap.file_path:
                    files_to_unlink.append(cap.file_path)
                self.db.delete(cap)
                captures_deleted += 1
            cluster_dir = unknowns_root / f"cluster_{cluster.id}"
            if cluster_dir.exists():
                dirs_to_remove.append(cluster_dir)
            UnknownCaptureService.reset_cooldown(cluster.id)
            self.db.delete(cluster)
            clusters_deleted += 1
        self.db.flush()
        # Commit immediately so row locks release BEFORE we start file IO.
        # The caller's session_scope() will also commit, but we want the
        # window to close as early as possible.
        self.db.commit()

        # ----- Phase 2: file IO (no DB locks held) -----
        files_deleted = 0
        bytes_freed = 0
        for path_str in files_to_unlink:
            p = Path(path_str)
            try:
                if p.exists():
                    size = p.stat().st_size
                    p.unlink()
                    files_deleted += 1
                    bytes_freed += size
            except OSError as exc:
                log.warning("Failed to remove capture file %s: %s", p, exc)

        for cluster_dir in dirs_to_remove:
            try:
                shutil.rmtree(cluster_dir, ignore_errors=True)
            except OSError as exc:
                log.warning("Failed to remove cluster dir %s: %s", cluster_dir, exc)

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
