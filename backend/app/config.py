import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Anchor relative paths to the BACKEND DIR (parent of this file's parent),
# not the process CWD. This is what makes `./storage/...` work no matter
# where the user launches uvicorn from (foreground, NSSM service, scheduler
# task, etc). Without this, paths break the moment the launcher's cwd
# differs from the backend dir.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _abs_under_backend(p: str | os.PathLike[str]) -> str:
    """Turn `./storage/foo` into an absolute path under the backend dir.

    Absolute paths the operator typed in .env are passed through unchanged
    so they can be relocated to a different drive (e.g. D:\\ai-storage)
    without touching the code.
    """
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    return str((_BACKEND_DIR / pp).resolve())


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
    # If JWT_SECRET_KEY is missing from .env (typical on a fresh install
    # before the installer's post-install hook ran), we auto-generate a
    # 64-char URL-safe secret and PERSIST it to .env so it stays stable
    # across restarts. This makes the app boot-safe on any machine — no
    # silent crash, no "Field required" Pydantic error — while still
    # giving the operator a real cryptographic secret. The first boot
    # writes it; every subsequent boot just reads it.
    JWT_SECRET_KEY: str = ""  # populated by _auto_jwt_secret validator
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
    # Worker reads at this rate. Detection is internally throttled to 1 Hz
    # regardless. Higher = smoother live preview, more CPU + bandwidth.
    CAMERA_FPS: int = 15
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

    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def _auto_jwt_secret(cls, v: str) -> str:
        """Generate + persist a JWT secret on first boot if missing.

        Why: the .env shipped by the installer has JWT_SECRET_KEY commented
        out for security (we don't ship a known-default secret). The first
        time uvicorn starts after install, this validator notices the
        empty value, generates a fresh 64-char URL-safe secret, and
        APPENDS it to the .env file so subsequent boots reuse it.

        Without this, a fresh install crashes on startup with "JWT_SECRET_KEY
        Field required" — the most common production-deploy footgun.
        """
        if v and v.strip() and v != "__GENERATED_BY_INSTALLER__":
            return v
        generated = secrets.token_urlsafe(48)
        try:
            env_path = _BACKEND_DIR / ".env"
            existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
            # Replace any prior JWT_SECRET_KEY line; otherwise append.
            new_line = f"JWT_SECRET_KEY={generated}\n"
            if "JWT_SECRET_KEY=" in existing:
                import re
                existing = re.sub(
                    r"^JWT_SECRET_KEY=.*$",
                    new_line.rstrip(),
                    existing,
                    flags=re.MULTILINE,
                )
                if not existing.endswith("\n"):
                    existing += "\n"
                env_path.write_text(existing, encoding="utf-8")
            else:
                with open(env_path, "a", encoding="utf-8") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    f.write(new_line)
        except Exception:
            # Persisting failed (read-only fs, AV lock, etc.) — still
            # return the generated secret so the app boots. Next restart
            # will generate a new one (invalidating sessions, but app
            # works).
            pass
        return generated

    @field_validator("FACE_MATCH_THRESHOLD")
    @classmethod
    def _threshold_range(cls, v: float) -> float:
        if not 0.0 < v < 1.0:
            raise ValueError("FACE_MATCH_THRESHOLD must be in (0, 1)")
        return v

    @field_validator(
        "STORAGE_ROOT",
        "TRAINING_DIR",
        "SNAPSHOT_DIR",
        "UNKNOWNS_DIR",
        "FACE_MODEL_ROOT",
        "LOG_DIR",
        mode="after",
    )
    @classmethod
    def _anchor_storage_paths(cls, v: str) -> str:
        """Make storage paths CWD-independent.

        `./storage/foo` becomes `<backend_dir>/storage/foo` so the app
        finds its data regardless of how it was launched. Absolute paths
        like `D:\\ai-storage` are kept as-is so the operator can move
        large data off the system drive.
        """
        return _abs_under_backend(v)

    @field_validator("FACE_TRAIN_MIN_IMAGES", "FACE_TRAIN_MAX_IMAGES")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    @model_validator(mode="after")
    def _reanchor_child_storage_paths(self) -> "Settings":
        """Re-anchor child storage paths under STORAGE_ROOT.

        If the operator sets STORAGE_ROOT=D:/ai-storage but leaves
        TRAINING_DIR/SNAPSHOT_DIR/UNKNOWNS_DIR/FACE_MODEL_ROOT at their
        defaults, those defaults were anchored to `<backend_dir>/storage/...`
        by `_anchor_storage_paths`, defeating the STORAGE_ROOT override.
        Detect that case (child path lives under the *default* backend
        storage dir while STORAGE_ROOT points elsewhere) and re-anchor
        each child path under the actual STORAGE_ROOT.
        """
        default_storage = (_BACKEND_DIR / "storage").resolve()
        actual_storage = Path(self.STORAGE_ROOT).resolve()
        if actual_storage == default_storage:
            return self
        child_attrs = {
            "TRAINING_DIR": "training_images",
            "SNAPSHOT_DIR": "snapshots",
            "UNKNOWNS_DIR": "unknowns",
            "FACE_MODEL_ROOT": "models",
        }
        for attr, leaf in child_attrs.items():
            current = Path(getattr(self, attr)).resolve()
            try:
                current.relative_to(default_storage)
            except ValueError:
                # Operator set an explicit non-default child path — respect it.
                continue
            object.__setattr__(self, attr, str(actual_storage / leaf))
        return self

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
