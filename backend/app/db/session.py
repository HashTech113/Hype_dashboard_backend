from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_ScopedSession: scoped_session[Session] | None = None


def _build_engine() -> Engine:
    settings = get_settings()
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
