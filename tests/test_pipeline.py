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
    pipeline.run_stage(db_session, job.id, 1)          # data ingestion needs no AI: allowed
    for n in (2, 3, 4, 5, 8, 9):
        with pytest.raises(pipeline.GateError):
            pipeline.run_stage(db_session, job.id, n)
    s0_intake.confirm_level(db_session, sf.id)
    pipeline.run_stage(db_session, job.id, 2)          # no audio → nothing to do, but the gate opens


def test_stage8_blocked_by_open_flags(db_session, tmp_path, monkeypatch):
    job, sf = _job(db_session, tmp_path, level=1)
    s0_intake.set_attendance(db_session, job.id, [{"session": "s", "count": 8}])
    t = Theme(job_id=job.id, label="x", summary="y", status="confirmed", decided_by="community", n_people=1,
              people_count=1)
    db_session.add(t); db_session.flush()
    db_session.add(IdentifyFlag(theme_id=t.id, kind="small_n", detail="1 person")); db_session.flush()
    with pytest.raises(pipeline.GateError, match="identifiability"):
        pipeline.run_stage(db_session, job.id, 8)


def test_stages_7_and_8_need_attendance_and_hand_counts(db_session, tmp_path):
    job, sf = _job(db_session, tmp_path, level=1)
    t = Theme(job_id=job.id, label="Parks", summary="y", status="confirmed", decided_by="community")
    db_session.add(t); db_session.flush()
    for n in (7, 8):
        with pytest.raises(pipeline.GateError, match="came to each session"):
            pipeline.run_stage(db_session, job.id, n)
    s0_intake.set_attendance(db_session, job.id, [{"session": "Mon", "count": 12}])
    with pytest.raises(pipeline.GateError, match="Parks"):
        pipeline.run_stage(db_session, job.id, 7)
    assert pipeline.status(db_session, job.id)["uncounted"] == ["Parks"]
    t.people_count = 5; db_session.flush()
    assert pipeline.status(db_session, job.id)["uncounted"] == []


def test_attendance_rows_are_checked(db_session, tmp_path):
    job, _ = _job(db_session, tmp_path, level=1)
    with pytest.raises(ValueError):
        s0_intake.set_attendance(db_session, job.id, [{"session": "", "count": 3}])
    with pytest.raises(ValueError):
        s0_intake.set_attendance(db_session, job.id, [{"session": "Mon", "count": "lots"}])
    s0_intake.set_attendance(db_session, job.id, [{"session": "Mon", "count": "7"}, {"session": "Tue", "count": 5}])
    assert s0_intake.attendance_total(job) == 12


def test_agreed_theme_is_community_only_and_survives_level3(db_session, tmp_path):
    job, sf = _job(db_session, tmp_path, level=2, confirmed=True)
    with pytest.raises(PermissionError):
        s0_intake.add_agreed_theme(db_session, job.id, "Parks", "", actor_role="facilitator")
    t = s0_intake.add_agreed_theme(db_session, job.id, "Parks", "More shade.")
    u = Unit(job_id=job.id, file_id=sf.id, source_type="text", source_id=0, text="t", redacted_text="t",
             speaker_key=f"file:{sf.id}", level=2)
    db_session.add(u); db_session.flush()
    db_session.add(ThemeQuote(theme_id=t.id, unit_id=u.id)); db_session.flush()
    pipeline.change_level(db_session, sf.id, 3)
    db_session.refresh(t)
    assert t.status == "confirmed" and t.agreed_upfront     # the community's theme stays, minus that quote


def test_raise_to_level3_cascades(db_session, tmp_path, monkeypatch):
    job, sf = _job(db_session, tmp_path, level=2, confirmed=True)
    u = Unit(job_id=job.id, file_id=sf.id, source_type="text", source_id=0, text="t", redacted_text="t",
             speaker_key=f"file:{sf.id}", level=2)
    db_session.add(u); db_session.flush()
    t = Theme(job_id=job.id, label="only from this file", summary="s", status="confirmed",
              decided_by="community", level=2, n_people=1)
    db_session.add(t); db_session.flush()
    db_session.add(ThemeQuote(theme_id=t.id, unit_id=u.id)); db_session.flush()

    pipeline.change_level(db_session, sf.id, 3)
    db_session.refresh(u); db_session.refresh(t); db_session.refresh(sf)
    assert sf.level == 3 and sf.level_confirmed_by_community is False
    assert u.excluded is True
    assert t.status == "unsupported"
    assert db_session.query(ThemeQuote).filter_by(theme_id=t.id).count() == 0


def test_lowering_from_level3_needs_the_community_again(db_session, tmp_path):
    from vcnity.stages._gate import ai_allowed

    job, sf = _job(db_session, tmp_path, level=3, confirmed=True)
    assert not ai_allowed(sf)
    pipeline.change_level(db_session, sf.id, 2)
    assert sf.level == 2 and sf.level_confirmed_by_community is False
    assert not ai_allowed(sf)  # Level 2 stays shut until a community reviewer confirms the new level
    s0_intake.confirm_level(db_session, sf.id)
    assert ai_allowed(sf)


def test_status_reports_every_stage(db_session, tmp_path):
    job, sf = _job(db_session, tmp_path, level=1)
    st = pipeline.status(db_session, job.id)
    by_n = {s["n"]: s for s in st["stages"]}
    assert list(by_n) == list(range(1, 10))     # stage 1 is intake and ingest together
    assert by_n[1]["done"] is False             # consent + level, but not converted yet
    sf.provenance = {"ingested_path": "x.txt"}; db_session.flush()
    assert pipeline.status(db_session, job.id)["stages"][0]["done"] is True
    assert by_n[2]["done"] is False             # nothing transcribed yet
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


def test_reset_job_keeps_raw_input_and_removes_outputs(db_session, tmp_path):
    from vcnity.models import AICall, Artefact, Concern, Pseudonym, Report, Segment

    job, sf = _job(db_session, tmp_path, level=2, confirmed=True)
    sf.provenance = {"ingested_path": "x.txt"}; sf.names_checked = True
    child = SourceFile(job_id=job.id, filename="deck_slide1_1.png", kind="image", level=2, path="p.png",
                       sha256="1" * 64, consent_id=sf.consent_id, provenance={"embedded_in": sf.filename})
    db_session.add(child); db_session.flush()
    db_session.add_all([Segment(file_id=sf.id, variant="without", start_s=0, end_s=1, text="t"),
                        Artefact(file_id=child.id, verbatim_text="HI")])
    u = Unit(job_id=job.id, file_id=sf.id, source_type="text", source_id=0, text="t", redacted_text="t",
             speaker_key="k", level=2)
    db_session.add(u); db_session.flush()
    t = s0_intake.add_agreed_theme(db_session, job.id, "Parks", "shade")
    db_session.add_all([ThemeQuote(theme_id=t.id, unit_id=u.id), IdentifyFlag(theme_id=t.id, kind="small_n"),
                        Report(job_id=job.id, kind="client", markdown="# r"),
                        Pseudonym(job_id=job.id, real="Priya", fake="Alex", source="person"),
                        Concern(job_id=job.id, stage=2, text="worried"),
                        AICall(job_id=job.id, stage=4, provider="p", is_local=True, level=2, model="m", purpose="x")])
    s0_intake.set_attendance(db_session, job.id, [{"session": "Mon", "count": 4}])
    exports = tmp_path / "exports"; exports.mkdir()
    (exports / f"job{job.id}_client.docx").write_bytes(b"x")
    (exports / "job999999_client.docx").write_bytes(b"other job")

    out = pipeline.reset_job(db_session, job.id, exports_dir=exports)
    db_session.expire_all()
    assert out["themes_removed"] == 1 and out["slide_pictures_removed"] == 1 and out["exports_removed"] == 1
    for model in (Theme, Unit, Report, Pseudonym):
        assert db_session.query(model).filter_by(job_id=job.id).count() == 0
    assert db_session.query(Segment).filter_by(file_id=sf.id).count() == 0
    files = db_session.query(SourceFile).filter_by(job_id=job.id).all()
    assert [f.id for f in files] == [sf.id]                                  # the raw upload stays
    kept = files[0]
    assert kept.level == 2 and kept.level_confirmed_by_community and kept.consent_id
    assert kept.provenance == {} and not kept.names_checked
    j = db_session.get(Job, job.id)
    assert j.status == "intake" and j.attendance == []
    assert db_session.query(Concern).filter_by(job_id=job.id).count() == 1  # people's concerns stay
    assert db_session.query(AICall).filter_by(job_id=job.id).count() == 1   # the audit log is never rewritten
    assert (exports / "job999999_client.docx").exists()
