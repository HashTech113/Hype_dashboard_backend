from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.config import get_settings
from app.core.exceptions import AppError
from app.core.logger import configure_logging, get_logger
from app.db.session import dispose_engine
from app.services.auth_service import bootstrap_admin
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.services.settings_service import get_settings_service
from app.workers.camera_manager import CameraManager

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info("Starting %s", settings.APP_NAME)

    bootstrap_admin()
    get_settings_service().load()

    face_service = FaceService()
    face_service.load()
    embedding_cache = EmbeddingCache()
    embedding_cache.load_from_db()

    camera_manager = CameraManager(
        face_service=face_service,
        embedding_cache=embedding_cache,
    )

    app.state.face_service = face_service
    app.state.embedding_cache = embedding_cache
    app.state.camera_manager = camera_manager

    camera_manager.start_all()

    try:
        yield
    finally:
        log.info("Shutting down %s", settings.APP_NAME)
        camera_manager.stop_all()
        dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        debug=settings.APP_DEBUG,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message},
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
