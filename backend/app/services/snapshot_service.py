from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core.constants import EventType
from app.core.logger import get_logger
from app.utils.image_utils import crop_bbox, write_jpeg
from app.utils.time_utils import to_local

log = get_logger(__name__)

_JPEG_QUALITY = 85
_CROP_PAD = 0.25


@dataclass
class StorageStats:
    root: str
    total_files: int
    total_bytes: int
    oldest_date: str | None
    newest_date: str | None


@dataclass
class PurgeResult:
    removed_files: int
    removed_bytes: int
    removed_dirs: int


class SnapshotService:
    """Event-based snapshot persistence.

    Layout: {SNAPSHOT_DIR}/YYYY-MM-DD/{employee_id}/{HHMMSS}_{EVENT}_{uuid}.jpg
    """

    def save_event_snapshot(
        self,
        *,
        employee_id: int,
        event_type: EventType,
        frame_bgr: np.ndarray,
        bbox: tuple[int, int, int, int] | None,
        captured_at: datetime,
    ) -> str:
        settings = get_settings()
        local_ts = to_local(captured_at)
        date_dir = local_ts.strftime("%Y-%m-%d")
        dir_path = Path(settings.SNAPSHOT_DIR) / date_dir / str(employee_id)

        image = crop_bbox(frame_bgr, bbox, pad=_CROP_PAD) if bbox is not None else frame_bgr
        if image.size == 0:
            image = frame_bgr

        filename = (
            f"{local_ts.strftime('%H%M%S')}_"
            f"{event_type.value}_"
            f"{uuid.uuid4().hex[:8]}.jpg"
        )
        full_path = dir_path / filename
        write_jpeg(full_path, image, quality=_JPEG_QUALITY)

        log.debug(
            "Snapshot saved path=%s event=%s emp=%s size=%dx%d",
            full_path,
            event_type.value,
            employee_id,
            image.shape[1],
            image.shape[0],
        )
        return str(full_path)

    # ------------------------------------------------------------------
    # Retention / stats
    # ------------------------------------------------------------------

    def storage_stats(self) -> StorageStats:
        settings = get_settings()
        root = Path(settings.SNAPSHOT_DIR)
        if not root.exists():
            return StorageStats(str(root), 0, 0, None, None)

        total_files = 0
        total_bytes = 0
        dates: set[str] = set()
        for date_dir in root.iterdir():
            if not date_dir.is_dir():
                continue
            # Accept both new layout (YYYY-MM-DD) and legacy (YYYY)
            if self._parse_date_dir(date_dir.name) is not None:
                dates.add(date_dir.name)
            for p in date_dir.rglob("*.jpg"):
                try:
                    total_files += 1
                    total_bytes += p.stat().st_size
                except OSError:
                    continue

        sorted_dates = sorted(dates)
        return StorageStats(
            root=str(root),
            total_files=total_files,
            total_bytes=total_bytes,
            oldest_date=sorted_dates[0] if sorted_dates else None,
            newest_date=sorted_dates[-1] if sorted_dates else None,
        )

    def purge_before(self, cutoff: date) -> PurgeResult:
        """Delete snapshot files dated before `cutoff` (exclusive).

        Walks `{SNAPSHOT_DIR}/YYYY-MM-DD/` directories and removes any whose
        parsed date is < cutoff. Returns counts of what was removed. Files
        whose directory name does not match the layout are left untouched.
        """
        settings = get_settings()
        root = Path(settings.SNAPSHOT_DIR)
        if not root.exists():
            return PurgeResult(0, 0, 0)

        removed_files = 0
        removed_bytes = 0
        removed_dirs = 0

        for date_dir in root.iterdir():
            if not date_dir.is_dir():
                continue
            parsed = self._parse_date_dir(date_dir.name)
            if parsed is None or parsed >= cutoff:
                continue
            for p in date_dir.rglob("*"):
                if p.is_file():
                    try:
                        size = p.stat().st_size
                        p.unlink()
                        removed_files += 1
                        removed_bytes += size
                    except OSError as exc:
                        log.warning("Failed to remove %s: %s", p, exc)
            try:
                shutil.rmtree(date_dir, ignore_errors=True)
                removed_dirs += 1
            except OSError as exc:
                log.warning("Failed to rmdir %s: %s", date_dir, exc)

        log.info(
            "Purged snapshots before %s: %d files (%d bytes), %d dirs",
            cutoff,
            removed_files,
            removed_bytes,
            removed_dirs,
        )
        return PurgeResult(
            removed_files=removed_files,
            removed_bytes=removed_bytes,
            removed_dirs=removed_dirs,
        )

    @staticmethod
    def _parse_date_dir(name: str) -> date | None:
        try:
            return date.fromisoformat(name)
        except ValueError:
            return None
