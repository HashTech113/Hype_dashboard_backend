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
            return self._matrix, list(self._ids), list(self._entries)

    def size(self) -> int:
        with self._lock:
            return 0 if self._matrix is None else int(self._matrix.shape[0])

    def employee_count(self) -> int:
        with self._lock:
            return len(self._entries)
