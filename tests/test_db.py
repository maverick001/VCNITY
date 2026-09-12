import numpy as np

from vcnity.models import Job, SourceFile, Unit


def test_roundtrip_and_vector(db_session):
    job = Job(name="t", brief="b")
    db_session.add(job)
    db_session.flush()
    f = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=2, path="x", sha256="0" * 64)
    db_session.add(f)
    db_session.flush()
    u = Unit(
        job_id=job.id, file_id=f.id, source_type="segment", source_id=1, text="hi",
        redacted_text="hi", speaker_key="S1", level=2, embedding=[0.0] * 768,
    )
    db_session.add(u)
    db_session.flush()
    db_session.expire_all()
    got = db_session.get(Unit, u.id)
    assert np.asarray(got.embedding).shape == (768,)
    assert got.excluded is False


def test_bad_level_rejected(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    job = Job(name="t")
    db_session.add(job)
    db_session.flush()
    db_session.add(SourceFile(job_id=job.id, filename="a", kind="audio", level=9, path="x", sha256="0" * 64))
    with pytest.raises(IntegrityError):
        db_session.flush()
