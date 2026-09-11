"""Shared fixtures. The embedded Postgres starts once per test session in a
scratch directory under ~/.vcnity so nothing lands in the Google Drive folder."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

TEST_HOME = Path.home() / ".vcnity" / "test"
os.environ["VCNITY_HOME"] = str(TEST_HOME)


@pytest.fixture(scope="session")
def pg_uri():
    from vcnity import db

    if TEST_HOME.exists():
        shutil.rmtree(TEST_HOME, ignore_errors=True)
    TEST_HOME.mkdir(parents=True, exist_ok=True)
    uri = db.start_pg(TEST_HOME / "pgdata")
    db.init_db(uri)
    yield uri
    db.stop_pg()


@pytest.fixture()
def db_session(pg_uri):
    from vcnity import db

    engine = db.get_engine(pg_uri)
    conn = engine.connect()
    trans = conn.begin()
    from sqlalchemy.orm import Session

    s = Session(bind=conn)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()
