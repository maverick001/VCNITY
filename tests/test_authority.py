import json
from dataclasses import replace

import pytest

from vcnity.models import IdentifyFlag, Job, Review, SourceFile, Theme, ThemeQuote, Unit
from vcnity.stages import s6_signoff, s7_identify


def _theme(db_session, n_people=2, level=1, text="the lights are broken"):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a", kind="text", level=level, level_confirmed_by_community=True,
                   path="x", sha256="0" * 64)
    db_session.add(f); db_session.flush()
    t = Theme(job_id=job.id, label="Lighting", summary="Lights.", status="draft", level=level)
    db_session.add(t); db_session.flush()
    for i in range(n_people):
        u = Unit(job_id=job.id, file_id=f.id, source_type="text", source_id=i, text=text,
                 redacted_text=text, speaker_key=f"file:{f.id}:{i}", level=level)
        db_session.add(u); db_session.flush()
        db_session.add(ThemeQuote(theme_id=t.id, unit_id=u.id))
    t.n_people = n_people
    db_session.flush()
    return job, t


def test_community_decision_locks_out_analyst(db_session):
    job, t = _theme(db_session)
    s6_signoff.review(db_session, t.id, actor_role="community", action="confirm")
    assert t.status == "confirmed" and t.decided_by == "community"
    with pytest.raises(s6_signoff.AuthorityError):
        s6_signoff.review(db_session, t.id, actor_role="analyst", action="fix", label="Analyst's label")
    with pytest.raises(s6_signoff.AuthorityError):
        s6_signoff.review(db_session, t.id, actor_role="analyst", action="reject")
    assert db_session.get(Theme, t.id).label == "Lighting"


def test_community_fix_sticks_and_is_logged(db_session):
    job, t = _theme(db_session)
    s6_signoff.review(db_session, t.id, actor_role="community", action="fix",
                      label="Dark carpark", summary="It is dark.", note="we said dark, not broken")
    assert t.status == "fixed" and t.label == "Dark carpark" and t.summary == "It is dark."
    r = db_session.query(Review).filter_by(theme_id=t.id).one()
    assert r.actor_role == "community" and r.before["label"] == "Lighting" and r.after["label"] == "Dark carpark"


def test_analyst_may_only_note_before_decision(db_session):
    job, t = _theme(db_session)
    s6_signoff.review(db_session, t.id, actor_role="analyst", action="note", note="looks thin")
    assert t.status == "draft" and t.decided_by is None and "looks thin" in t.review_note
    with pytest.raises(s6_signoff.AuthorityError):
        s6_signoff.review(db_session, t.id, actor_role="analyst", action="confirm")


def test_add_theme_requires_a_quote(db_session):
    job, t = _theme(db_session)
    with pytest.raises(ValueError):
        s6_signoff.add_theme(db_session, job.id, "New", "Added by community", quote_unit_ids=[])
    unit_id = t.quotes[0].unit_id
    added = s6_signoff.add_theme(db_session, job.id, "New", "Added by community", quote_unit_ids=[unit_id])
    assert added.status == "added" and added.decided_by == "community" and added.n_people == 1


def test_small_n_flag_and_cut_needs_reason(db_session, monkeypatch):
    job, t = _theme(db_session, n_people=2)
    s6_signoff.review(db_session, t.id, actor_role="community", action="confirm")
    monkeypatch.setattr(s7_identify, "settings", replace(s7_identify.settings, small_n=3))
    monkeypatch.setattr(s7_identify.router, "call",
                        lambda session, **kw: json.dumps({"identifying": False, "why": ""}))
    flags = s7_identify.run(db_session, job.id)
    assert [f.kind for f in flags] == ["small_n"]
    with pytest.raises(ValueError):
        s7_identify.decide(db_session, flags[0].id, "cut", reason="   ")
    s7_identify.decide(db_session, flags[0].id, "cut", reason="two people in a group of twelve")
    assert db_session.get(Theme, t.id).status == "cut" and db_session.get(Theme, t.id).decided_by == "community"


def test_pii_flag_from_regex(db_session, monkeypatch):
    job, t = _theme(db_session, n_people=3, text="call me on 0412 345 678 about the lights")
    s6_signoff.review(db_session, t.id, actor_role="community", action="confirm")
    monkeypatch.setattr(s7_identify.router, "call",
                        lambda session, **kw: json.dumps({"identifying": False, "why": ""}))
    flags = s7_identify.run(db_session, job.id)
    assert [f.kind for f in flags] == ["pii"]
    s7_identify.decide(db_session, flags[0].id, "keep", reason="number is a public helpline")
    assert db_session.get(Theme, t.id).status == "confirmed"
    assert s7_identify.open_flags(db_session, job.id) == []
