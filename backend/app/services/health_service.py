"""Comprehensive system health check (P0.3 + lifecycle visibility).

Used by:
  - GET /health        — simple liveness probe (HTTP 200 if process is up)
  - GET /health/ready  — full readiness: DB OK? model loaded? disk OK?
  - GET /health/disk   — disk-space-only quick report for the dashboard

The "ready" endpoint is what an external monitor / NSSM service-failure
trigger should poll. If `ready` returns 503, the system is up but
unhealthy — alert and rotate logs to keep the operator informed.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logger import get_logger

log = get_logger(__name__)


# When free disk on STORAGE_ROOT drops below this fraction, mark `degraded`.
# 5% is the alarm threshold; 1% is the critical threshold (system at risk).
_DISK_WARN_FREE_FRACTION = 0.05
_DISK_CRIT_FREE_FRACTION = 0.01

# Absolute floor — even on a huge disk, less than 1 GB free is dangerous.
_DISK_MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB


@dataclass
class DiskUsage:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    free_fraction: float
    state: str  # OK / WARN / CRITICAL / ERROR


def disk_usage_for(path: str) -> DiskUsage:
    """Best-effort disk-usage report. Returns ERROR state on any I/O failure."""
    try:
        # Resolve to an existing parent if the path itself doesn't exist
        # (e.g. STORAGE_ROOT hasn't been created yet on first run).
        p = Path(path).resolve()
        while not p.exists() and p != p.parent:
            p = p.parent
        usage = shutil.disk_usage(str(p))
        free_frac = usage.free / usage.total if usage.total > 0 else 0.0
        if usage.free < _DISK_MIN_FREE_BYTES or free_frac < _DISK_CRIT_FREE_FRACTION:
            state = "CRITICAL"
        elif free_frac < _DISK_WARN_FREE_FRACTION:
            state = "WARN"
        else:
            state = "OK"
        return DiskUsage(
            path=str(p),
            total_bytes=usage.total,
            used_bytes=usage.used,
            free_bytes=usage.free,
            free_fraction=float(free_frac),
            state=state,
        )
    except Exception as exc:
        log.warning("disk_usage probe failed for %s: %s", path, exc)
        return DiskUsage(
            path=path,
            total_bytes=0,
            used_bytes=0,
            free_bytes=0,
            free_fraction=0.0,
            state="ERROR",
        )


def storage_breakdown() -> dict:
    """Per-storage-area sizes — useful for "what's eating my disk" diagnosis."""
    settings = get_settings()
    out = {}
    for label, raw_path in [
        ("training_images", settings.TRAINING_DIR),
        ("snapshots", settings.SNAPSHOT_DIR),
        ("unknowns", settings.UNKNOWNS_DIR),
        ("models", settings.FACE_MODEL_ROOT),
        ("logs", settings.LOG_DIR),
    ]:
        try:
            total = 0
            count = 0
            p = Path(raw_path)
            if p.exists():
                for root, _dirs, files in os.walk(p):
                    for fn in files:
                        try:
                            total += os.path.getsize(os.path.join(root, fn))
                            count += 1
                        except OSError:
                            pass
            out[label] = {
                "path": str(raw_path),
                "exists": p.exists(),
                "file_count": count,
                "total_bytes": total,
            }
        except Exception as exc:
            out[label] = {"path": str(raw_path), "error": str(exc)}
    return out


def disk_report() -> dict:
    """One JSON report covering all storage drives we care about."""
    settings = get_settings()
    storage = disk_usage_for(settings.STORAGE_ROOT)
    logs = disk_usage_for(settings.LOG_DIR)
    return {
        "storage_root": _du_dict(storage),
        "logs": _du_dict(logs),
        "breakdown": storage_breakdown(),
        "overall_state": _worst_state([storage.state, logs.state]),
    }


def _worst_state(states: list[str]) -> str:
    order = ["OK", "WARN", "CRITICAL", "ERROR"]
    worst = "OK"
    for s in states:
        if order.index(s) > order.index(worst):
            worst = s
    return worst


def _du_dict(du: DiskUsage) -> dict:
    return {
        "path": du.path,
        "total_bytes": du.total_bytes,
        "used_bytes": du.used_bytes,
        "free_bytes": du.free_bytes,
        "free_fraction": round(du.free_fraction, 4),
        "state": du.state,
    }


def readiness_report(db: Session, *, embedding_cache, camera_manager) -> dict:
    """Full readiness: DB + face model + disk + camera workers."""
    checks: dict[str, dict] = {}
    overall_ok = True

    # DB
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ok": True, "detail": "SELECT 1 returned"}
    except Exception as exc:
        checks["database"] = {"ok": False, "detail": str(exc)[:200]}
        overall_ok = False

    # Face model
    try:
        loaded = bool(embedding_cache)
        checks["embedding_cache"] = {
            "ok": loaded,
            "detail": "loaded" if loaded else "not initialized",
        }
        if not loaded:
            overall_ok = False
    except Exception as exc:
        checks["embedding_cache"] = {"ok": False, "detail": str(exc)[:200]}
        overall_ok = False

    # Camera workers — counts AND performance regression check.
    #
    # We previously only verified that workers were "tracked" (i.e. the
    # manager knew about them). A worker can be tracked and STREAMING
    # while silently processing frames at 1/6th its expected rate —
    # a class of bug a code audit can't catch without load. This check
    # closes that gap: for every STREAMING camera with a known native
    # FPS, we compare actual processing rate against expected. If the
    # ratio drops below `_DEGRADED_RATIO`, we mark the check as
    # degraded so the operator's monitoring stack sees it.
    try:
        statuses = camera_manager.status() if camera_manager else []
        degraded: list[dict] = []
        for s in statuses:
            if not s.get("is_running") or s.get("health_state") != "STREAMING":
                continue
            expected = s.get("fps_effective") or 0
            run = s.get("seconds_since_start") or 0
            frames = s.get("processed_frames") or 0
            # Need at least 10s of runtime + 1 fps expected to make a
            # statistically-meaningful claim. Skip warmup window.
            if run < 10.0 or expected < 1:
                continue
            actual = frames / run
            # Anything below half the expected fps is a real regression.
            # 0.5 is forgiving — the worker's own publish rate has overhead
            # (detection runs every 1s) so steady-state achievable is
            # around 60-80% of native. Drop below 50% = something's wrong.
            ratio = actual / expected
            if ratio < 0.5:
                degraded.append({
                    "camera_id": s.get("camera_id"),
                    "name": s.get("camera_name"),
                    "expected_fps": expected,
                    "actual_fps": round(actual, 2),
                    "ratio_pct": round(ratio * 100, 1),
                })
        if degraded:
            checks["camera_workers"] = {
                "ok": False,
                "detail": (
                    f"{len(degraded)} camera(s) underperforming "
                    f"(actual fps < 50% of expected)"
                ),
                "count": len(statuses),
                "degraded": degraded,
            }
            overall_ok = False
        else:
            checks["camera_workers"] = {
                "ok": True,
                "detail": f"{len(statuses)} workers tracked",
                "count": len(statuses),
            }
    except Exception as exc:
        checks["camera_workers"] = {"ok": False, "detail": str(exc)[:200]}
        overall_ok = False

    # Disk
    disk = disk_report()
    checks["disk"] = {
        "ok": disk["overall_state"] in ("OK", "WARN"),
        "state": disk["overall_state"],
        "free_bytes_storage": disk["storage_root"]["free_bytes"],
    }
    if disk["overall_state"] == "CRITICAL":
        overall_ok = False

    return {
        "ok": overall_ok,
        "checks": checks,
        "disk": disk,
    }
