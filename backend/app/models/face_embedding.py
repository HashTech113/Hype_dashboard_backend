from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.face_image import EmployeeFaceImage


class EmployeeFaceEmbedding(Base):
    __tablename__ = "employee_face_embeddings"
    __table_args__ = (
        Index("ix_employee_face_embeddings_employee_model", "employee_id", "model_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_id: Mapped[int] = mapped_column(
        ForeignKey("employee_face_images.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=512)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, default="buffalo_l")
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    employee: Mapped["Employee"] = relationship(back_populates="face_embeddings")
    image: Mapped["EmployeeFaceImage"] = relationship(back_populates="embeddings")
