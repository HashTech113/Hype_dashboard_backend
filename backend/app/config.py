from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str

    # API
    APP_NAME: str = "AI CCTV Attendance"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = False

    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Bootstrap admin
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = "ChangeMe@123"

    # Face recognition
    FACE_MODEL_NAME: str = "buffalo_l"
    FACE_MODEL_ROOT: str = "./storage/models"
    FACE_PROVIDER: Literal["CPUExecutionProvider", "CUDAExecutionProvider"] = "CPUExecutionProvider"
    FACE_DET_SIZE: int = 640
    FACE_MATCH_THRESHOLD: float = 0.45
    FACE_MIN_QUALITY: float = 0.50
    FACE_TRAIN_MIN_IMAGES: int = 5
    FACE_TRAIN_MAX_IMAGES: int = 20

    # Camera pipeline
    CAMERA_FPS: int = 1
    CAMERA_COOLDOWN_SECONDS: int = 5
    CAMERA_HEALTH_INTERVAL_SECONDS: int = 10
    CAMERA_HEARTBEAT_TIMEOUT_SECONDS: int = 30
    RTSP_CONNECT_TIMEOUT_MS: int = 5000
    RTSP_READ_TIMEOUT_MS: int = 5000
    RTSP_RECONNECT_MAX_SECONDS: int = 30

    # Storage
    STORAGE_ROOT: str = "./storage"
    TRAINING_DIR: str = "./storage/training_images"
    SNAPSHOT_DIR: str = "./storage/snapshots"
    UNKNOWNS_DIR: str = "./storage/unknowns"

    # Timezone
    TIMEZONE: str = "Asia/Kolkata"

    # CORS — comma-separated origin list via env (CORS_ALLOW_ORIGINS=http://a,http://b)
    CORS_ALLOW_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> list[str] | object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    LOG_MAX_BYTES: int = 104857600
    LOG_BACKUP_COUNT: int = 5

    @field_validator("FACE_MATCH_THRESHOLD")
    @classmethod
    def _threshold_range(cls, v: float) -> float:
        if not 0.0 < v < 1.0:
            raise ValueError("FACE_MATCH_THRESHOLD must be in (0, 1)")
        return v

    @field_validator("FACE_TRAIN_MIN_IMAGES", "FACE_TRAIN_MAX_IMAGES")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    def ensure_directories(self) -> None:
        for path in (
            self.STORAGE_ROOT,
            self.TRAINING_DIR,
            self.SNAPSHOT_DIR,
            self.UNKNOWNS_DIR,
            self.FACE_MODEL_ROOT,
            self.LOG_DIR,
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()  # type: ignore[call-arg]
    s.ensure_directories()
    return s
