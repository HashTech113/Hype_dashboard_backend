from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from app.api.v1 import api_router
from app.config import get_settings
from app.core.exceptions import AppError
from app.core.logger import configure_logging, get_logger
from app.db.session import dispose_engine, get_sessionmaker
from app.services.auth_service import bootstrap_admin
from app.services.embedding_cache import EmbeddingCache
from app.services.face_service import FaceService
from app.services.go2rtc_service import get_go2rtc_service
from app.services.health_service import disk_report, readiness_report
from app.services.settings_service import get_settings_service
from app.workers.camera_manager import CameraManager

log = get_logger(__name__)


def _auto_migrate() -> None:
    """Run Alembic `upgrade head` automatically on app start.

    Why: the installer's post-install hook calls Alembic once, but if the
    operator copies the install to a new machine, or restores from
    backup, or pulls a newer version of the code, the DB might be at an
    older revision. Auto-migrating on boot makes the app self-healing —
    you can drop a fresh codebase on an old DB and it just upgrades.

    Failures here are LOGGED but DO NOT abort startup. If migrations
    can't run (DB down, permission issue), the app still boots so the
    operator can see the /health/ready endpoint flagging the problem.
    """
    from pathlib import Path

    try:
        from alembic import command
        from alembic.config import Config

        backend_dir = Path(__file__).resolve().parent.parent
        ini_path = backend_dir / "alembic.ini"
        if not ini_path.exists():
            log.warning("alembic.ini not found at %s — skipping auto-migrate", ini_path)
            return
        cfg = Config(str(ini_path))
        # Make script_location absolute so Alembic resolves it regardless
        # of where uvicorn was launched from.
        scripts_dir = backend_dir / "migrations"
        if scripts_dir.exists():
            cfg.set_main_option("script_location", str(scripts_dir))
        command.upgrade(cfg, "head")
        log.info("Database is at the latest migration revision")
    except Exception:
        log.exception(
            "Auto-migrate failed — the app will still boot but tables may be "
            "out of date. Run 'alembic upgrade head' manually to recover."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info("Starting %s", settings.APP_NAME)

    # Self-heal the DB schema BEFORE bootstrap_admin (which needs the
    # `admins` table to exist).
    _auto_migrate()

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

    # Start go2rtc bridge in the background. Non-blocking: if it fails to
    # download/start, the system still works — frontend falls back to
    # WebSocket JPEG streaming.
    go2rtc = get_go2rtc_service()
    try:
        go2rtc.start()
        app.state.go2rtc = go2rtc
        if go2rtc.is_running:
            log.info("go2rtc bridge running — WebRTC live preview available")
        else:
            log.info(
                "go2rtc bridge unavailable: %s — using WebSocket fallback",
                go2rtc.last_error,
            )
    except Exception:
        log.exception("go2rtc startup error — using WebSocket fallback")
        app.state.go2rtc = go2rtc

    camera_manager.start_all()

    # After workers start, sync active cameras into go2rtc so the WebRTC
    # streams are ready when the frontend asks for them.
    if go2rtc.is_running:
        try:
            from app.db.session import session_scope
            from app.repositories.camera_repo import CameraRepository

            with session_scope() as db:
                cams = CameraRepository(db).list_active()
                go2rtc.sync_cameras([(c.id, c.rtsp_url) for c in cams])
            log.info("go2rtc synced %d active camera(s)", len(cams))
        except Exception:
            log.exception("go2rtc camera sync failed at startup")

    try:
        yield
    finally:
        log.info("Shutting down %s", settings.APP_NAME)
        camera_manager.stop_all()
        try:
            go2rtc.stop()
        except Exception:
            log.warning("go2rtc stop on shutdown raised")
        dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        debug=settings.APP_DEBUG,
        lifespan=lifespan,
    )

    # CORS — allow localhost variants plus any LAN IP origin the operator
    # might use from another device on the same network (e.g. opening the
    # dashboard from a tablet at 192.168.1.50:3000 when the server is on
    # 192.168.1.20:8000). We use a regex so we don't have to enumerate
    # every NIC. Operator can still override CORS_ALLOW_ORIGINS in .env
    # to lock down to specific hostnames.
    lan_origin_regex = (
        r"^https?://"
        r"(localhost|127\.0\.0\.1|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})"
        r"(:\d+)?$"
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOW_ORIGINS,
        allow_origin_regex=lan_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # H8 fix: request_id middleware + catch-all exception handler.
    # Every request gets a short random ID — surfaced as the
    # X-Request-ID response header and stamped on the request state so
    # exception handlers + logs can correlate user-reported failures with
    # backend log lines.
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or secrets.token_hex(6)
        request.state.request_id = rid
        try:
            response = await call_next(request)
        except Exception:
            # Let the exception handlers below produce the response; just
            # make sure the rid is available to them (already on state).
            raise
        response.headers["X-Request-ID"] = rid
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message, "request_id": rid},
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.exception_handler(OperationalError)
    async def db_op_error_handler(request: Request, exc: OperationalError) -> JSONResponse:
        """Transient DB outage -> 503 so the frontend retry policy kicks in."""
        rid = getattr(request.state, "request_id", None)
        log.error("DB OperationalError request_id=%s: %s", rid, exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "database_unavailable",
                "message": "Database is temporarily unavailable. Please try again in a moment.",
                "request_id": rid,
            },
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.exception_handler(DBAPIError)
    async def db_api_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
        """Other persistent DB errors -> 500 with a sanitized message."""
        rid = getattr(request.state, "request_id", None)
        log.exception("DBAPIError request_id=%s", rid)
        return JSONResponse(
            status_code=500,
            content={
                "error": "database_error",
                "message": "A database error occurred.",
                "request_id": rid,
            },
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all so non-AppError errors don't leak stack traces to clients.

        The request_id is in both the JSON body and the response header so the
        operator can trace 'request_id=abc123 failed' from a user report to
        the matching log line.
        """
        rid = getattr(request.state, "request_id", None)
        log.exception(
            "Unhandled exception request_id=%s path=%s method=%s",
            rid,
            request.url.path,
            request.method,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred. Please contact support with this request_id if it persists.",
                "request_id": rid,
            },
            headers={"X-Request-ID": rid} if rid else None,
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        """Liveness probe — returns 200 as long as the HTTP server is up.

        Intentionally does NOT check the DB / model / disk so a slow DB
        doesn't take the service-supervisor's liveness check down with it.
        Use /health/ready for full readiness.
        """
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready(request: Request) -> JSONResponse:
        """Full readiness check. Returns 503 if anything critical is down.

        Designed to be polled by NSSM / Windows Service Manager or an
        external uptime monitor. Includes DB + face model + disk + worker
        status in a single response.
        """
        SessionLocal = get_sessionmaker()
        db = SessionLocal()
        try:
            cache = getattr(request.app.state, "embedding_cache", None)
            mgr = getattr(request.app.state, "camera_manager", None)
            report = readiness_report(
                db, embedding_cache=cache, camera_manager=mgr
            )
            status_code = 200 if report["ok"] else 503
            return JSONResponse(status_code=status_code, content=report)
        finally:
            db.close()

    @app.get("/health/disk", tags=["health"])
    async def health_disk() -> dict:
        """Standalone disk-space report (cheaper than full readiness).

        Polled by the dashboard widget every 30-60s — lighter cost than
        /health/ready since it doesn't touch the DB or workers.
        """
        return disk_report()

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
