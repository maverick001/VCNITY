import pytest

from vcnity.models import Job, Report, SourceFile, Theme, ThemeQuote, Unit
from vcnity.stages import s8_report, s9_reportback


def _job(db_session):
    job = Job(name="FQI session", brief="P1: The community was invited to help.")
    db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=2, level_confirmed_by_community=True,
                   path="x", sha256="0" * 64, provenance={"duration_s": 725.1})
    db_session.add(f); db_session.flush()
    units = []
    for i in range(5):  # 5 distinct people in the job
        u = Unit(job_id=job.id, file_id=f.id, source_type="segment", source_id=i, text=f"quote {i}",
                 redacted_text=f"quote {i}", speaker_key=f"{f.id}:S{i}", level=2)
        db_session.add(u); units.append(u)
    db_session.flush()

    def theme(label, status, members):
        t = Theme(job_id=job.id, label=label, summary=f"{label} summary.", status=status, level=2,
                  decided_by="community" if status != "draft" else None, n_people=len(members))
        db_session.add(t); db_session.flush()
        for m in members:
            db_session.add(ThemeQuote(theme_id=t.id, unit_id=units[m].id))
        return t

    theme("Lighting", "confirmed", [0, 1, 2])
    theme("Parking", "fixed", [3, 4])
    theme("Added one", "added", [0])
    theme("Rejected", "rejected", [1, 2])
    theme("Cut one", "cut", [3])
    theme("Still draft", "draft", [4])
    db_session.flush()
    return job


def test_theme_table_includes_only_signed_off_and_counts(db_session):
    job = _job(db_session)
    table = s8_report.theme_table(db_session, job.id)
    labels = [r["label"] for r in table]
    assert labels == ["Lighting", "Parking", "Added one"]
    light = table[0]
    assert light["n"] == 3 and light["m"] == 5 and light["pct"] == 60


def test_render_has_council_sections(db_session):
    job = _job(db_session)
    md = s8_report.render_markdown(job, s8_report.theme_table(db_session, job.id),
                                   s8_report.how_we_engaged(db_session, job.id), "Findings text.")
    for h in ("## Background", "## How we engaged", "## What the community told us", "## Findings", "## Sources"):
        assert h in md
    assert "3 of 5 participants (60%)" in md
    assert "Rejected" not in md and "Cut one" not in md


def test_run_export_gated_on_dual_approval(db_session, monkeypatch, tmp_path):
    job = _job(db_session)
    monkeypatch.setattr(s8_report.router, "call", lambda session, **kw: "Findings drafted from the table.")
    rep = s8_report.run(db_session, job.id)
    assert rep.kind == "client" and "Findings drafted" in rep.markdown
    with pytest.raises(PermissionError):
        s8_report.export(db_session, rep.id, tmp_path / "out")
    s8_report.approve(db_session, rep.id, "community")
    with pytest.raises(PermissionError):
        s8_report.export(db_session, rep.id, tmp_path / "out")
    s8_report.approve(db_session, rep.id, "analyst")
    md, docx = s8_report.export(db_session, rep.id, tmp_path / "out")
    assert md.exists() and docx.exists() and docx.suffix == ".docx"


def test_reportback_plain_language(db_session, monkeypatch):
    job = _job(db_session)
    monkeypatch.setattr(s8_report.router, "call", lambda session, **kw: "Findings.")
    s8_report.run(db_session, job.id)
    seen = {}
    def fake(session, **kw):
        seen.update(kw); return "Here is what you told us, in plain words."
    monkeypatch.setattr(s9_reportback.router, "call", fake)
    rb = s9_reportback.run(db_session, job.id)
    assert rb.kind == "reportback" and "plain words" in rb.markdown
    assert seen["level"] == 2 and seen["redacted"] is True
    with pytest.raises(PermissionError):
        s9_reportback.send(db_session, rb.id)
    s8_report.approve(db_session, rb.id, "community"); s8_report.approve(db_session, rb.id, "analyst")
    assert s9_reportback.send(db_session, rb.id).sent is True
