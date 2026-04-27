from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class FaceImageRead(ORMModel):
    id: int
    employee_id: int
    file_path: str
    file_hash: str | None
    width: int | None
    height: int | None
    uploaded_by: int | None
    created_at: datetime


class EmbeddingRead(ORMModel):
    id: int
    employee_id: int
    image_id: int
    dim: int
    model_name: str
    quality_score: float
    created_at: datetime


class TrainingResult(BaseModel):
    employee_id: int
    accepted: int
    rejected: int
    total_embeddings: int
    errors: list[str]
