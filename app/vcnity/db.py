"""Embedded PostgreSQL (pgserver) + SQLAlchemy session handling.

No install needed on the demo laptop: pgserver ships the Postgres binaries and
the pgvector extension for Windows, macOS and Linux.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

_server = None
_uri: str | None = None
_engine = None
_Session = None


def start_pg(pg_dir: Path | None = None) -> str:
    """Start (or reuse) the embedded server and return its SQLAlchemy URI."""
    global _server, _uri
    if _uri:
        return _uri
    import pgserver

    pg_dir = Path(pg_dir or settings.pg_dir)
    pg_dir.mkdir(parents=True, exist_ok=True)
    _server = pgserver.get_server(pg_dir)
    raw = _server.get_uri()
    _uri = raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return _uri


def stop_pg() -> None:
    global _server, _uri, _engine, _Session
    if _engine is not None:
        _engine.dispose()
    if _server is not None:
        try:
            _server.cleanup()
        except Exception:  # pragma: no cover - best effort on shutdown
            pass
    _server = _uri = _engine = _Session = None


def get_engine(uri: str | None = None):
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(uri or start_pg(), future=True)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db(uri: str | None = None) -> None:
    from . import models  # noqa: F401  (registers tables)

    engine = get_engine(uri)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    models.Base.metadata.create_all(engine)


@contextmanager
def session():
    get_engine()
    s: Session = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
