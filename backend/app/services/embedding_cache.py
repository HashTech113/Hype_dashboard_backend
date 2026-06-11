from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np

from app.core.logger import get_logger
from app.db.session import session_scope
from app.repositories.embedding_repo import EmbeddingRepository

log = get_logger(__name__)


@dataclass(frozen=True)
class CacheEntry:
    employee_id: int
    employee_code: str
    employee_name: str
    vectors: np.ndarray  # shape (n, dim), L2-normalized


class EmbeddingCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: list[CacheEntry] = []
        self._matrix: np.ndarray | None = None
        self._ids: list[int] = []

    @staticmethod
    def _unpack(vec: bytes, dim: int) -> np.ndarray:
        arr = np.frombuffer(vec, dtype=np.float32)
        if arr.size != dim:
            raise ValueError(f"Vector size mismatch: expected {dim}, got {arr.size}")
        n = np.linalg.norm(arr)
        return arr / n if n > 0 else arr

    @staticmethod
    def pack(vec: np.ndarray) -> bytes:
        return np.ascontiguousarray(vec.astype(np.float32)).tobytes()

    def load_from_db(self) -> None:
        with session_scope() as db:
            repo = EmbeddingRepository(db)
            rows = repo.list_active_with_employee()

        grouped: dict[int, list[np.ndarray]] = {}
        meta: dict[int, tuple[str, str]] = {}
        for emb, emp, _img in rows:
            try:
                v = self._unpack(emb.vector, emb.dim)
            except ValueError:
                log.warning("Skipping corrupt embedding id=%s", emb.id)
                continue
            grouped.setdefault(emp.id, []).append(v)
            meta[emp.id] = (emp.employee_code, emp.name)

        entries: list[CacheEntry] = []
        flat_vectors: list[np.ndarray] = []
        flat_ids: list[int] = []
        for emp_id, vecs in grouped.items():
            mat = np.vstack(vecs).astype(np.float32)
            code, name = meta[emp_id]
            entries.append(
                CacheEntry(employee_id=emp_id, employee_code=code, employee_name=name, vectors=mat)
            )
            flat_vectors.extend(vecs)
            flat_ids.extend([emp_id] * len(vecs))

        matrix = (
            np.vstack(flat_vectors).astype(np.float32)
            if flat_vectors
            else None
        )

        with self._lock:
            self._entries = entries
            self._matrix = matrix
            self._ids = flat_ids
        log.info("Embedding cache loaded: %d employees, %d vectors", len(entries), len(flat_ids))

    def snapshot(self) -> tuple[np.ndarray | None, list[int], list[CacheEntry]]:
        with self._lock:
            # Return a COPY of the matrix to prevent stale-reference races:
            # append_vectors() / load_from_db() rebuild self._matrix via
            # np.vstack and reassign the attribute. If we returned a bare
            # reference, a recognition thread holding it after lock release
            # could see a matrix whose row-count no longer matches the _ids
            # list captured concurrently with subsequent writes. Copying
            # under the lock guarantees (matrix, ids, entries) are mutually
            # consistent and immune to any later in-place mutation.
            matrix_copy = None if self._matrix is None else self._matrix.copy()
            return matrix_copy, list(self._ids), list(self._entries)

    def size(self) -> int:
        with self._lock:
            return 0 if self._matrix is None else int(self._matrix.shape[0])

    def employee_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def append_vectors(
        self,
        *,
        employee_id: int,
        employee_code: str,
        employee_name: str,
        new_vectors: list[np.ndarray],
    ) -> None:
        """Incrementally add vectors for one employee — used by auto-enroll
        and single-image training adds (H4 fix).

        Avoids the full O(N) reload from DB that load_from_db() does, which
        was previously called on the camera worker thread after every
        auto-enrollment — stalling RTSP reads for hundreds of ms while the
        whole cache rebuilt.

        Each vector is L2-normalized to match load_from_db()'s contract.
        If the employee already has an entry, the new vectors are appended
        to their existing matrix.
        """
        if not new_vectors:
            return
        # Normalize outside the lock (CPU-bound, no shared state)
        normed = []
        for v in new_vectors:
            v = np.ascontiguousarray(v, dtype=np.float32).reshape(-1)
            n = np.linalg.norm(v)
            normed.append(v / n if n > 0 else v)
        add_matrix = np.vstack(normed).astype(np.float32)
        with self._lock:
            existing_idx = next(
                (i for i, e in enumerate(self._entries) if e.employee_id == employee_id),
                None,
            )
            if existing_idx is not None:
                old = self._entries[existing_idx]
                combined = np.vstack([old.vectors, add_matrix]).astype(np.float32)
                self._entries[existing_idx] = CacheEntry(
                    employee_id=employee_id,
                    employee_code=old.employee_code,
                    employee_name=old.employee_name,
                    vectors=combined,
                )
            else:
                self._entries.append(
                    CacheEntry(
                        employee_id=employee_id,
                        employee_code=employee_code,
                        employee_name=employee_name,
                        vectors=add_matrix,
                    )
                )
            # Rebuild the flat matrix in-place from the in-memory entries
            # (cheap — no DB hit). Keeps recognition's matmul shape correct.
            if self._matrix is None or self._matrix.size == 0:
                self._matrix = add_matrix.copy()
                self._ids = [employee_id] * add_matrix.shape[0]
            else:
                self._matrix = np.vstack([self._matrix, add_matrix]).astype(np.float32)
                self._ids.extend([employee_id] * add_matrix.shape[0])
