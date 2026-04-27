from __future__ import annotations

from sqlalchemy import Boolean, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import CameraType
from app.db.base import Base, TimestampMixin


class Camera(Base, TimestampMixin):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    rtsp_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    camera_type: Mapped[CameraType] = mapped_column(
        SAEnum(CameraType, name="camera_type"), nullable=False, index=True
    )
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
