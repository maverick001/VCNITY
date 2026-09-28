import json

import numpy as np

from vcnity.models import Artefact, Job, Pseudonym, Segment, SourceFile, Theme, ThemeQuote, Unit
from vcnity.stages import s0_intake, s4_themes, s5_evidence


def _job_with_material(db_session):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    aud = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=2, level_confirmed_by_community=True,
                     path="x", sha256="a" * 64)
    img = SourceFile(job_id=job.id, filename="p.jpg", kind="image", level=2, level_confirmed_by_community=True,
                     path="y", sha256="b" * 64)
    l3 = SourceFile(job_id=job.id, filename="s.m4a", kind="audio", level=3, level_confirmed_by_community=True,
                    path="z", sha256="c" * 64)
    db_session.add_all([aud, img, l3]); db_session.flush()
    db_session.add_all([
        Segment(file_id=aud.id, variant="with_wordlist", start_s=0, end_s=2, speaker="S0",
                text="The carpark lighting is terrible at night and Priya agrees"),
        Segment(file_id=aud.id, variant="with_wordlist", start_s=2, end_s=4, speaker="S1",
                text="Nobody feels safe walking there after dark"),
        Segment(file_id=aud.id, variant="with_wordlist", start_s=4, end_s=5, speaker="S1", text="yeah"),
        Segment(file_id=aud.id, variant="without", start_s=0, end_s=2, speaker="S0",
                text="the car park lighting is terrible at night and priya agrees"),
        Segment(file_id=l3.id, variant="with_wordlist", start_s=0, end_s=2, speaker="S9",
                text="This is restricted cultural knowledge that must not be used"),
    ])
    db_session.add(Artefact(file_id=img.id, verbatim_text="PATIENCE\nKINDNESS", description="red marker"))
    db_session.flush()
    return job, aud, img, l3


def test_build_units_skips_level3_and_short_and_swaps_names(db_session):
    job, aud, img, l3 = _job_with_material(db_session)
    s4_themes.add_name(db_session, job.id, "Priya", "wordlist")
    n = s4_themes.build_units(db_session, job.id)
    units = db_session.query(Unit).filter_by(job_id=job.id).all()
    assert n == 3 and len(units) == 3                      # 2 long segments + 1 artefact; no "yeah", nothing from L3
    assert not any(u.file_id == l3.id for u in units)
    seg_unit = next(u for u in units if "lighting" in u.text)
    assert "Priya" in seg_unit.text and "Priya" not in seg_unit.redacted_text and "Alex" in seg_unit.redacted_text
    assert seg_unit.speaker_key == f"{aud.id}:S0" and seg_unit.level == 2
    art_unit = next(u for u in units if u.source_type == "artefact")
    assert "PATIENCE" in art_unit.text and art_unit.speaker_key == f"file:{img.id}"


def test_cluster_three_groups():
    rng = np.random.default_rng(0)
    base = np.eye(768)[:3]
    X = np.vstack([base[i] + rng.normal(0, 0.01, 768) for i in range(3) for _ in range(4)])
    labels = s4_themes.cluster(X, min_size=2)
    assert len(labels) == 12
    groups = [set(labels[i * 4:(i + 1) * 4]) for i in range(3)]
    assert all(len(g) == 1 for g in groups) and len({next(iter(g)) for g in groups}) == 3


def _checked(db_session, *files):
    for f in files:
        f.names_checked = True
    db_session.flush()


def test_run_creates_themes_with_member_quotes(db_session, monkeypatch):
    monkeypatch.setattr(s4_themes, "person_names", lambda _p: ["Priya"])
    job, aud, img, _l3 = _job_with_material(db_session)
    _checked(db_session, aud, img)
    monkeypatch.setattr(s4_themes, "embed", lambda texts: np.eye(768)[: len(texts)] if len(texts) <= 768 else None)
    monkeypatch.setattr(s4_themes, "cluster", lambda X, min_size: [0, 0, 1][: len(X)])
    seen = []
    def fake_call(session, **kw):
        seen.append(kw)
        return json.dumps({"label": "Safety at night", "summary": "People say the carpark is dark."})
    monkeypatch.setattr(s4_themes.router, "call", fake_call)
    rep = s4_themes.run(db_session, job.id)
    themes = db_session.query(Theme).filter_by(job_id=job.id).all()
    assert len(themes) == 2 and rep["themes"] == 2
    labels = [kw for kw in seen if kw["purpose"] == "theme-label"]
    assert labels and all(kw["redacted"] is True and kw["level"] == 2 for kw in labels)
    assert all("Priya" not in kw["prompt"] for kw in labels)
    big = max(themes, key=lambda t: len(t.quotes))
    assert len(big.quotes) == 2 and big.n_people == 2 and big.status == "draft"


def test_evidence_structural_and_grounding(db_session, monkeypatch):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a", kind="text", level=1, path="x", sha256="0" * 64)
    db_session.add(f); db_session.flush()
    u = Unit(job_id=job.id, file_id=f.id, source_type="text", source_id=1, text="lights are broken",
             redacted_text="lights are broken", speaker_key="file:1", level=1)
    db_session.add(u); db_session.flush()
    t = Theme(job_id=job.id, label="Lighting", summary="The lights are broken.", status="draft", level=1)
    db_session.add(t); db_session.flush()
    db_session.add(ThemeQuote(theme_id=t.id, unit_id=u.id)); db_session.flush()

    assert s5_evidence.check_structural(db_session, t.id) is True
    monkeypatch.setattr(s5_evidence.router, "call",
                        lambda session, **kw: json.dumps({"unsupported": False, "sentence": ""}))
    assert s5_evidence.run(db_session, job.id)["unsupported"] == []
    assert db_session.get(Theme, t.id).status == "draft"

    monkeypatch.setattr(s5_evidence.router, "call",
                        lambda session, **kw: json.dumps({"unsupported": True, "sentence": "The lights are broken."}))
    assert s5_evidence.run(db_session, job.id)["unsupported"] == [t.id]
    assert db_session.get(Theme, t.id).status == "unsupported"

    t.status = "draft"; u.excluded = True; db_session.flush()
    assert s5_evidence.check_structural(db_session, t.id) is False


def _stub_models(monkeypatch, names=()):
    monkeypatch.setattr(s4_themes, "person_names", lambda _p: [])
    monkeypatch.setattr(s4_themes, "embed", lambda texts: np.eye(768)[: len(texts)])
    monkeypatch.setattr(s4_themes, "cluster", lambda X, min_size: [0] * len(X))

    calls = []

    def fake_call(session, **kw):
        calls.append(kw)
        if kw["purpose"].startswith("name-scan"):
            return json.dumps({"names": list(names)})
        return json.dumps({"label": "L", "summary": "S"})
    monkeypatch.setattr(s4_themes.router, "call", fake_call)
    return calls


def test_stage4_stops_for_the_name_check_then_sorts(db_session, monkeypatch):
    calls = _stub_models(monkeypatch, names=["Priya", "Zanzibar Ghost"])   # the second isn't in the text
    job, aud, img, _l3 = _job_with_material(db_session)
    out = s4_themes.run(db_session, job.id)
    assert set(out["waiting_name_check"]) == {aud.filename, img.filename}
    assert db_session.query(Theme).filter_by(job_id=job.id).count() == 0     # nothing sorted yet
    reals = [p.real for p in db_session.query(Pseudonym).filter_by(job_id=job.id)]
    assert reals == ["Priya"]                                                # invented names are ignored
    scan = [kw for kw in calls if kw["purpose"].startswith("name-scan")]
    assert scan and all(kw["name_scan"] is True and kw["level"] == 2 for kw in scan)
    _checked(db_session, aud, img)
    out = s4_themes.run(db_session, job.id)
    assert "waiting_name_check" not in out and out["themes"] == 1
    assert len([kw for kw in calls if kw["purpose"].startswith("name-scan")]) == len(scan)  # not rescanned


def test_changing_the_names_needs_a_new_check(db_session, monkeypatch):
    _stub_models(monkeypatch)
    job, aud, img, _l3 = _job_with_material(db_session)
    s4_themes.run(db_session, job.id)
    _checked(db_session, aud, img)
    s4_themes.add_name(db_session, job.id, "Priya", "person")
    s4_themes.names_changed(db_session, job.id)
    assert not aud.names_checked and not img.names_checked
    u = next(u for u in db_session.query(Unit).filter_by(job_id=job.id) if "lighting" in u.text)
    assert "Priya" not in u.redacted_text


def test_rerun_after_signoff_keeps_the_signed_off_quotes(db_session, monkeypatch):
    _stub_models(monkeypatch)
    job, aud, img, _l3 = _job_with_material(db_session)
    _checked(db_session, aud, img)
    s4_themes.run(db_session, job.id)
    t = db_session.query(Theme).filter_by(job_id=job.id).one()
    t.status, t.decided_by = "confirmed", "community"
    db_session.flush()
    quotes = sorted(q.unit_id for q in t.quotes)
    s4_themes.run(db_session, job.id)                    # used to fail: units were deleted under their quotes
    db_session.refresh(t)
    assert sorted(q.unit_id for q in t.quotes) == quotes and t.status == "confirmed"


def test_sort_into_nearest_agreed_theme():
    X = np.eye(4)[:3]
    A = np.vstack([np.eye(4)[0], np.eye(4)[1]])
    assert s4_themes.sort_into(X, A, 0.5) == [0, 1, -1]
    assert s4_themes.sort_into(X, np.zeros((0, 4)), 0.5) == [-1, -1, -1]


def test_stage4_sorts_into_agreed_themes_and_suggests_the_rest(db_session, monkeypatch):
    _stub_models(monkeypatch)
    job, aud, img, _l3 = _job_with_material(db_session)
    _checked(db_session, aud, img)
    agreed = s0_intake.add_agreed_theme(db_session, job.id, "Safety at night", "Feeling unsafe after dark.")
    # units come in id order: 2 segments then the artefact; the agreed theme text embeds as row 0 → unit 1 matches
    monkeypatch.setattr(s4_themes, "embed",
                        lambda texts: np.eye(768)[: len(texts)] if len(texts) > 1 else np.eye(768)[:1])
    out = s4_themes.run(db_session, job.id)
    db_session.refresh(agreed)
    assert out["sorted"] == 1 and len(agreed.quotes) == 1 and agreed.status == "confirmed"
    assert agreed.level == 2                             # took the level of what was sorted into it
    drafts = db_session.query(Theme).filter_by(job_id=job.id, status="draft").all()
    assert len(drafts) == 1 and len(drafts[0].quotes) == 2


def test_evidence_check_leaves_community_themes_alone(db_session):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    t = s0_intake.add_agreed_theme(db_session, job.id, "Parks", "More shade in parks.")
    out = s5_evidence.run(db_session, job.id)
    assert out["unsupported"] == [] and db_session.get(Theme, t.id).status == "confirmed"
