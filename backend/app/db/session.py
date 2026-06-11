from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app.config import get_settings
from app.core.logger import get_logger

log = get_logger(__name__)


def _ensure_database_exists(database_url: str) -> None:
    """Create the target Postgres database if it doesn't exist.

    Removes the "you must create the database manually before running
    the app" footgun from the install procedure. We connect to the
    `postgres` admin DB on the same server, check for our target DB,
    CREATE it if missing.

    Idempotent — silently returns if the DB already exists, raises only
    on permission / connectivity errors that the operator needs to fix.

    Skips silently for non-Postgres URLs (e.g. sqlite for testing).
    """
    try:
        url = make_url(database_url)
    except Exception:
        return
    if not url.drivername.startswith("postgresql"):
        return
    target_db = url.database
    if not target_db or target_db == "postgres":
        return

    admin_url = url.set(database="postgres")
    try:
        admin_engine = create_engine(
            admin_url,
            isolation_level="AUTOCOMMIT",  # CREATE DATABASE can't run in a tx
            future=True,
        )
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": target_db},
            ).scalar()
            if not exists:
                # Quote the identifier with double-quotes so names with
                # hyphens / mixed case work. The :n placeholder doesn't
                # work for DDL identifiers — we have to inline.
                safe_name = target_db.replace('"', '""')
                conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
                log.warning(
                    "Created missing database '%s' on first boot", target_db
                )
        admin_engine.dispose()
    except (OperationalError, ProgrammingError) as exc:
        log.warning(
            "Could not auto-create database '%s' (%s). The operator must "
            "create it manually if it doesn't exist.",
            target_db,
            exc,
        )
    except Exception:
        log.exception(
            "Unexpected error during database auto-create for '%s'", target_db
        )

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_ScopedSession: scoped_session[Session] | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    # Create the target DB if missing — handles the fresh-install case
    # where Postgres is up but ai_attendance hasn't been created yet.
    _ensure_database_exists(settings.DATABASE_URL)
    return create_engine(
        settings.DATABASE_URL,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


def get_scoped_session() -> scoped_session[Session]:
    global _ScopedSession
    if _ScopedSession is None:
        _ScopedSession = scoped_session(get_sessionmaker())
    return _ScopedSession


def get_db() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def dispose_engine() -> None:
    global _engine, _SessionLocal, _ScopedSession
    if _ScopedSession is not None:
        _ScopedSession.remove()
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _ScopedSession = None
