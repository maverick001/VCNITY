import json

import pytest

from vcnity import pipeline
from vcnity.models import IdentifyFlag, Job, SourceFile, Theme, ThemeQuote, Unit
from vcnity.stages import concerns, s0_intake


def _job(db_session, tmp_path, level=2, confirmed=False):
    job = s0_intake.create_job(db_session, "j")
    f = tmp_path / "n.txt"
    f.write_text("Facilitator notes about the session with more than six words in them.")
    sf = s0_intake.add_file(db_session, job.id, f, level=level, consent_label="c", consent_scope="s")
    if confirmed:
        s0_intake.confirm_level(db_session, sf.id)
    return job, sf


def test_gate_refuses_ai_stages_on_unconfirmed_level2(db_session, tmp_path):
    job, sf = _job(db_session, tmp_path, level=2, confirmed=False)
    pipeline.run_stage(db_session, job.id, 0)
    pipeline.run_stage(db_session, job.id, 1)          # ingest needs no AI: allowed
    for n in (2, 3, 4, 5, 8, 9):
        with pytest.raises(pipeline.GateError):
            pipeline.run_stage(db_session, job.id, n)
    s0_intake.confirm_level(db_session, sf.id)
    pipeline.run_stage(db_session, job.id, 2)          # no audio → nothing to do, but the gate opens


def test_stage8_blocked_by_open_flags(db_session, tmp_path, monkeypatch):
    job, sf = _job(db_session, tmp_path, level=1)
    t = Theme(job_id=job.id, label="x", summary="y", status="confirmed", decided_by="community", n_people=1)
    db_session.add(t); db_session.flush()
    db_session.add(IdentifyFlag(theme_id=t.id, kind="small_n", detail="1 person")); db_session.flush()
    with pytest.raises(pipeline.GateError):
        pipeline.run_stage(db_session, job.id, 8)


def test_raise_to_level3_cascades(db_session, tmp_path, monkeypatch):
    job, sf = _job(db_session, tmp_path, level=2, confirmed=True)
    u = Unit(job_id=job.id, file_id=sf.id, source_type="text", source_id=0, text="t", redacted_text="t",
             speaker_key=f"file:{sf.id}", level=2)
    db_session.add(u); db_session.flush()
    t = Theme(job_id=job.id, label="only from this file", summary="s", status="confirmed",
              decided_by="community", level=2, n_people=1)
    db_session.add(t); db_session.flush()
    db_session.add(ThemeQuote(theme_id=t.id, unit_id=u.id)); db_session.flush()

    pipeline.raise_level(db_session, sf.id, 3)
    db_session.refresh(u); db_session.refresh(t); db_session.refresh(sf)
    assert sf.level == 3 and sf.level_confirmed_by_community is False
    assert u.excluded is True
    assert t.status == "unsupported"
    assert db_session.query(ThemeQuote).filter_by(theme_id=t.id).count() == 0


def test_status_reports_every_stage(db_session, tmp_path):
    job, sf = _job(db_session, tmp_path, level=1)
    st = pipeline.status(db_session, job.id)
    assert [s["n"] for s in st["stages"]] == list(range(10))
    assert st["stages"][0]["done"] is True      # file has consent + level
    assert st["stages"][2]["done"] is False     # nothing transcribed yet
    assert st["waiting_level2"] == []


def test_concern_routing(db_session, tmp_path, monkeypatch):
    from dataclasses import replace
    job, sf = _job(db_session, tmp_path, level=1)
    monkeypatch.setattr(concerns, "settings", replace(concerns.settings, safety_contact="Dr A Person"))
    c = concerns.raise_concern(db_session, job.id, stage=6, text="someone said something that worried me")
    assert c.category is None and c.status == "new"
    c = concerns.sort_concern(db_session, c.id, "harm")
    assert c.routed_to == "Dr A Person" and c.level == 3 and c.status == "routed"
    c2 = concerns.raise_concern(db_session, job.id, stage=4, text="the AI got my words wrong")
    c2 = concerns.sort_concern(db_session, c2.id, "ai_error", material_level=2)
    assert c2.routed_to == "VCNITY analyst on this job" and c2.level == 2
