from __future__ import annotations

from pydantic import BaseModel


class IdentifyResult(BaseModel):
    matched: bool
    employee_id: int | None
    employee_code: str | None
    employee_name: str | None
    score: float
    second_best_score: float
    threshold: float
    face_quality: float


class CacheStats(BaseModel):
    employee_count: int
    total_vectors: int
    model_name: str
    threshold: float
