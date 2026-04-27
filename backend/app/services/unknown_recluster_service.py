"""HDBSCAN-based offline re-clustering for unknown faces.

The online capture pipeline (Module 3) is order-dependent: the first
sighting of a person creates a cluster, and slightly-different later
sightings may match or split depending on how borderline they were
against the current centroid. Over time this produces drift —
fragmentation (one person split across multiple clusters) is the most
common artifact; rare miss-merges (two people in one cluster) also
happen if the matching threshold was tuned loose.

This service does what production face-clustering systems (Apple
Photos, Google Photos) do: periodically re-run a global density-based
clustering algorithm over **all** captures' embeddings and reconcile
the results back to the existing clusters.

**Why HDBSCAN over DBSCAN/K-means:**

  * Density-based — no need to specify cluster count up front.
  * Variable density — DBSCAN's single `eps` fails on real-world data
    where some people have many photos (dense) and others have few
    (sparse). HDBSCAN handles both in one pass.
  * Stable — `cluster_selection_method='eom'` (Excess of Mass) gives
    repeatable, conservative clusterings well-suited to a feature
    where false merges are worse than false splits.
  * Industry-standard — McInnes et al.'s HDBSCAN was upstreamed into
    scikit-learn as `sklearn.cluster.HDBSCAN` in 1.3 (2023) and is now
    the canonical Python implementation. We use it directly so the
    feature inherits sklearn's release cadence and security audits.

**Distance metric:**

  * Embeddings are L2-normalized 512-d vectors. On the unit sphere,
    euclidean distance is monotonic with cosine distance:
        ‖a-b‖² = 2(1 - a·b)  for unit-norm a, b
    so HDBSCAN's default fast `metric='euclidean'` produces identical
    cluster shapes to `metric='cosine'` at a fraction of the cost.

**Reconciliation:**

  1. For each HDBSCAN group, choose a *primary* existing cluster:
     majority vote on captures' current `cluster_id`, ties broken by
     earliest `first_seen_at` (preserves continuity of the longest-
     standing cluster).
  2. Migrate every capture in the group to its primary cluster.
  3. Any cluster that ends up with zero KEEP captures is marked
     `MERGED` with `merged_into_cluster_id` = the destination that
     received the largest share of its captures. The cluster row is
     **never deleted** — its history (label, first_seen, etc.) stays
     queryable for audit.
  4. Centroids of all surviving clusters are recomputed from their
     KEEP captures (mean → re-normalize) so they reflect the new
     membership exactly.

Captures HDBSCAN labels as **noise** (-1) keep their existing cluster
assignment — noise often means "the only photo of this person", which
the admin still needs to see in the review queue.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import UnknownClusterStatus
from app.core.logger import get_logger
from app.models.unknown_face import UnknownFaceCapture, UnknownFaceCluster
from app.repositories.unknown_capture_repo import UnknownCaptureRepository
from app.repositories.unknown_cluster_repo import UnknownClusterRepository
from app.services.unknown_capture_service import UnknownCaptureService

log = get_logger(__name__)

_EMBEDDING_DIM = 512
_DEFAULT_MIN_CLUSTER_SIZE = 2  # tiny groups still form a cluster; singletons → noise
_DEFAULT_MIN_SAMPLES = 1  # mirror min_cluster_size loosely; keeps small groups alive


@dataclass(frozen=True)
class ReclusterOutcome:
    ran: bool
    reason: str  # "ok" | "too_few_captures" | "no_pending_clusters"
    captures_total: int
    clusters_before: int
    clusters_after_pending: int  # PENDING clusters surviving with KEEP captures
    clusters_merged: int
    captures_migrated: int
    noise_count: int
    duration_ms: int


class UnknownReclusterService:
    """Reconcile online-clustering drift with HDBSCAN.

    Construct one per DB session. Idempotent — calling it back-to-back is
    a no-op once clusters are stable. Safe to schedule (e.g. nightly cron)
    or trigger from an admin endpoint.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cluster_repo = UnknownClusterRepository(db)
        self.capture_repo = UnknownCaptureRepository(db)
        self._model_name = get_settings().FACE_MODEL_NAME

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        min_cluster_size: int = _DEFAULT_MIN_CLUSTER_SIZE,
        min_samples: int = _DEFAULT_MIN_SAMPLES,
    ) -> ReclusterOutcome:
        """Run a global HDBSCAN pass and apply the reconciliation.

        Returns a `ReclusterOutcome` with full counters for the API
        response. Raises only on infrastructure errors (DB, hdbscan
        import failure) — these propagate to the caller's session_scope
        for proper rollback.
        """
        t0 = time.monotonic()

        captures = self.capture_repo.list_keep_in_pending_clusters(
            model_name=self._model_name
        )
        if not captures:
            return self._empty_outcome("no_pending_clusters", t0)
        if len(captures) < max(2, min_cluster_size):
            return self._empty_outcome("too_few_captures", t0, captures_total=len(captures))

        # Deduplicate to a clean float32 matrix; track which captures we kept.
        kept_caps: list[UnknownFaceCapture] = []
        vectors: list[np.ndarray] = []
        for cap in captures:
            v = np.frombuffer(cap.embedding, dtype=np.float32)
            if v.size != _EMBEDDING_DIM:
                log.warning(
                    "Skipping capture id=%s with malformed embedding dim=%d",
                    cap.id,
                    v.size,
                )
                continue
            kept_caps.append(cap)
            vectors.append(v)

        if len(kept_caps) < max(2, min_cluster_size):
            return self._empty_outcome(
                "too_few_captures", t0, captures_total=len(kept_caps)
            )

        matrix = np.vstack(vectors).astype(np.float32)

        # Snapshot original assignment per capture (used for merge-destination resolution)
        original_cluster_id_per_capture: dict[int, int] = {
            cap.id: int(cap.cluster_id) for cap in kept_caps
        }

        # Snapshot every PENDING cluster currently in play (so we can resolve
        # `first_seen_at` tie-breaks without re-querying).
        pending_clusters = list(
            self.cluster_repo.list_by_status(
                UnknownClusterStatus.PENDING, limit=None, order_desc=False
            )
        )
        clusters_by_id: dict[int, UnknownFaceCluster] = {
            c.id: c for c in pending_clusters
        }
        clusters_before = len(clusters_by_id)

        # ---- HDBSCAN ----
        labels = self._run_hdbscan(
            matrix,
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
        )

        # ---- Bucket captures by HDBSCAN label ----
        groups: dict[int, list[UnknownFaceCapture]] = defaultdict(list)
        noise_count = 0
        for cap, lbl in zip(kept_caps, labels):
            if lbl == -1:
                noise_count += 1
                continue
            groups[int(lbl)].append(cap)

        # ---- Migrate captures to each group's primary cluster ----
        captures_migrated = 0
        affected_cluster_ids: set[int] = set()

        for grp_caps in groups.values():
            cluster_counts = Counter(int(c.cluster_id) for c in grp_caps)
            if len(cluster_counts) == 1:
                continue  # HDBSCAN agrees with the existing assignment
            primary_id = self._pick_primary(cluster_counts, clusters_by_id)
            for cap in grp_caps:
                if int(cap.cluster_id) != primary_id:
                    affected_cluster_ids.add(int(cap.cluster_id))
                    cap.cluster_id = primary_id
                    captures_migrated += 1
            affected_cluster_ids.add(primary_id)

        # Persist the FK updates before recomputing centroids
        self.db.flush()

        # ---- Reconcile each affected cluster ----
        clusters_merged = 0
        for cid in affected_cluster_ids:
            cluster = clusters_by_id.get(cid)
            if cluster is None:
                continue
            if cluster.status != UnknownClusterStatus.PENDING:
                continue

            new_centroid, new_count = self._recompute_centroid(cid)
            if new_centroid is None or new_count == 0:
                # All captures migrated away — mark MERGED with the dominant destination
                dest = self._pick_merge_destination(
                    cid, original_cluster_id_per_capture, kept_caps
                )
                cluster.status = UnknownClusterStatus.MERGED
                cluster.merged_into_cluster_id = dest
                cluster.member_count = 0
                clusters_merged += 1
                # Drop in-process cooldown so the cluster_id can be GC'd later
                UnknownCaptureService.reset_cooldown(cid)
                log.info(
                    "Recluster: cluster_id=%s emptied → MERGED into %s",
                    cid,
                    dest,
                )
            else:
                self.cluster_repo.update_after_capture(
                    cluster,
                    new_centroid=new_centroid.tobytes(),
                    new_centroid_dim=int(new_centroid.size),
                    new_member_count=new_count,
                    last_seen_at=cluster.last_seen_at,
                )

        self.db.flush()

        # ---- Survivors count: PENDING clusters that still have KEEP captures ----
        survivors = sum(
            1
            for c in clusters_by_id.values()
            if c.status == UnknownClusterStatus.PENDING and c.member_count > 0
        )

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.info(
            "Recluster done: captures=%d before=%d after=%d merged=%d migrated=%d noise=%d in %d ms",
            len(kept_caps),
            clusters_before,
            survivors,
            clusters_merged,
            captures_migrated,
            noise_count,
            elapsed_ms,
        )
        return ReclusterOutcome(
            ran=True,
            reason="ok",
            captures_total=len(kept_caps),
            clusters_before=clusters_before,
            clusters_after_pending=survivors,
            clusters_merged=clusters_merged,
            captures_migrated=captures_migrated,
            noise_count=noise_count,
            duration_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_hdbscan(
        matrix: np.ndarray,
        *,
        min_cluster_size: int,
        min_samples: int,
    ) -> np.ndarray:
        """Lazy-import HDBSCAN so the rest of the app boots even without
        scikit-learn (e.g. during partial dev environments).

        Uses `sklearn.cluster.HDBSCAN` (McInnes et al.'s algorithm
        upstreamed into scikit-learn 1.3+). API surface matches the
        original `hdbscan` package; we follow the same parameter
        recommendations for face embeddings.
        """
        from sklearn.cluster import HDBSCAN  # type: ignore[import-not-found]

        clusterer = HDBSCAN(
            metric="euclidean",
            min_cluster_size=int(max(2, min_cluster_size)),
            min_samples=int(max(1, min_samples)),
            cluster_selection_method="eom",
            # `allow_single_cluster=False` is deliberate: in this feature a
            # false merge (two real people lumped together → wrong employee
            # promotion) is far worse than a false split (admin sees two
            # cluster cards for the same person and merges them manually).
            # Setting it to True can collapse distinct populations when their
            # inter-distance is comparable to noisy intra-distances.
            allow_single_cluster=False,
        )
        return clusterer.fit_predict(matrix)

    @staticmethod
    def _pick_primary(
        cluster_counts: Counter,
        clusters_by_id: dict[int, UnknownFaceCluster],
    ) -> int:
        """Majority cluster wins. Tie-break: earliest `first_seen_at`."""
        max_count = max(cluster_counts.values())
        candidates = [cid for cid, n in cluster_counts.items() if n == max_count]
        if len(candidates) == 1:
            return int(candidates[0])
        # Tie-break by earliest first_seen_at; fall back to lowest id for
        # determinism if a candidate is missing from the snapshot.

        def sort_key(cid: int):
            cluster = clusters_by_id.get(cid)
            if cluster is None:
                return (float("inf"), cid)
            return (cluster.first_seen_at.timestamp(), cid)

        return int(min(candidates, key=sort_key))

    @staticmethod
    def _pick_merge_destination(
        emptied_cluster_id: int,
        original_cluster_id_per_capture: dict[int, int],
        kept_caps: list[UnknownFaceCapture],
    ) -> int | None:
        """Find the cluster id that absorbed the most of an emptied cluster's
        captures. Returns None if for some reason no destination dominates
        (shouldn't happen — we only mark MERGED when captures migrated out).
        """
        dest_counts: Counter[int] = Counter()
        for cap in kept_caps:
            if original_cluster_id_per_capture.get(cap.id) == emptied_cluster_id:
                dest_counts[int(cap.cluster_id)] += 1
        # Don't pick the cluster itself (means no migration happened)
        dest_counts.pop(emptied_cluster_id, None)
        if not dest_counts:
            return None
        return int(dest_counts.most_common(1)[0][0])

    def _recompute_centroid(
        self, cluster_id: int
    ) -> tuple[np.ndarray | None, int]:
        rows = self.capture_repo.list_keep_embeddings_for_cluster(cluster_id)
        if not rows:
            return None, 0
        vectors: list[np.ndarray] = []
        for blob, dim in rows:
            arr = np.frombuffer(blob, dtype=np.float32)
            if arr.size != dim or arr.size != _EMBEDDING_DIM:
                continue
            vectors.append(arr)
        if not vectors:
            return None, 0
        mat = np.vstack(vectors).astype(np.float32)
        mean = mat.mean(axis=0)
        n = float(np.linalg.norm(mean))
        if n <= 0.0:
            return None, len(vectors)
        return (mean / n).astype(np.float32), len(vectors)

    @staticmethod
    def _empty_outcome(
        reason: str, t0: float, *, captures_total: int = 0
    ) -> ReclusterOutcome:
        return ReclusterOutcome(
            ran=False,
            reason=reason,
            captures_total=captures_total,
            clusters_before=0,
            clusters_after_pending=0,
            clusters_merged=0,
            captures_migrated=0,
            noise_count=0,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
