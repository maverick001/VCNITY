"""Embedded PostgreSQL (pgserver) + SQLAlchemy session handling.

No install needed on the demo laptop: pgserver ships the Postgres binaries and
the pgvector extension for Windows, macOS and Linux.
"""
from __future__ import annotations

import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

_server = None
_uri: str | None = None
_engine = None
_Session = None

_PG_START_ATTEMPTS = 15
_PG_RETRY_DELAY_S = 4


def start_pg(pg_dir: Path | None = None) -> str:
    """Start (or reuse) the embedded server and return its SQLAlchemy URI."""
    global _server, _uri
    if _uri:
        return _uri
    import pgserver
    from pgserver.postgres_server import PostgresServer

    pg_dir = Path(pg_dir or settings.pg_dir)
    pg_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = pg_dir.expanduser().resolve()

    # pgserver waits at most 10s (hardcoded in the library) for Postgres to
    # report ready. WAL crash recovery after an unclean shutdown can take
    # longer than that even though the server finishes starting a few
    # seconds later, which would otherwise crash this whole process. Two
    # distinct races show up here: a subprocess.TimeoutExpired from the
    # initial pg_ctl wait, or an AssertionError from pgserver's "already
    # running" fast path reading postmaster.pid in the narrow window where
    # the process exists but hasn't flipped its status to "ready" yet.
    #
    # Either way, pgserver has already cached a half-constructed instance
    # under this pgdata (it registers itself before startup even begins), so
    # a plain retry just returns that broken instance instead of trying
    # again. Evict it first so the retry re-runs startup, which then finds
    # the now-running server via postmaster.pid and succeeds immediately.
    for attempt in range(1, _PG_START_ATTEMPTS + 1):
        try:
            _server = pgserver.get_server(pg_dir)
            break
        except (subprocess.TimeoutExpired, AssertionError):
            PostgresServer._instances.pop(resolved_dir, None)
            if attempt == _PG_START_ATTEMPTS:
                raise
            time.sleep(_PG_RETRY_DELAY_S)
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
