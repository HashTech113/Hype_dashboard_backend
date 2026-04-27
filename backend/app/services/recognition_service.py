from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.embedding_cache import EmbeddingCache
from app.services.settings_service import get_settings_service


@dataclass(frozen=True)
class MatchResult:
    employee_id: int | None
    score: float
    second_best_score: float


class RecognitionService:
    def __init__(self, cache: EmbeddingCache) -> None:
        self.cache = cache

    def match(self, embedding: np.ndarray, *, threshold: float | None = None) -> MatchResult:
        thr = (
            float(threshold)
            if threshold is not None
            else get_settings_service().get().face_match_threshold
        )
        matrix, ids, _ = self.cache.snapshot()
        if matrix is None or matrix.size == 0:
            return MatchResult(employee_id=None, score=0.0, second_best_score=0.0)

        q = embedding.astype(np.float32)
        n = np.linalg.norm(q)
        if n == 0:
            return MatchResult(employee_id=None, score=0.0, second_best_score=0.0)
        q = q / n

        sims = matrix @ q

        per_employee: dict[int, float] = {}
        for emp_id, s in zip(ids, sims):
            v = float(s)
            if emp_id not in per_employee or per_employee[emp_id] < v:
                per_employee[emp_id] = v

        ranked = sorted(per_employee.items(), key=lambda x: x[1], reverse=True)
        best_id, best_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0

        if best_score < thr:
            return MatchResult(employee_id=None, score=best_score, second_best_score=second)
        return MatchResult(employee_id=best_id, score=best_score, second_best_score=second)
