from vcnity.models import Artefact, Job, SourceFile
from vcnity.stages import s3_artefacts


def test_parse_vlm():
    out = s3_artefacts.parse_vlm(
        "PATIENCE\nKINDNESS [illegible]\nFRENDSHIP\n"
        "DESCRIPTION: Red marker on white butcher paper. A drawing of two faces."
    )
    assert out["illegible_count"] == 1
    assert out["verbatim_text"].startswith("PATIENCE")
    assert "FRENDSHIP" in out["verbatim_text"]
    assert out["description"].startswith("Red marker")


def test_parse_vlm_without_description_line():
    out = s3_artefacts.parse_vlm("only words here")
    assert out["verbatim_text"] == "only words here" and out["description"] == ""


def test_run_uses_router_and_skips_level3(db_session, monkeypatch, tmp_path):
    job = Job(name="j"); db_session.add(job); db_session.flush()
    pic = tmp_path / "p.jpg"; pic.write_bytes(b"x")
    ok = SourceFile(job_id=job.id, filename="ok.jpg", kind="image", level=2, level_confirmed_by_community=True,
                    path=str(pic), sha256="a" * 64, provenance={"ingested_path": str(pic)})
    l3 = SourceFile(job_id=job.id, filename="l3.jpg", kind="image", level=3, level_confirmed_by_community=True,
                    path=str(pic), sha256="b" * 64, provenance={"ingested_path": str(pic)})
    db_session.add_all([ok, l3]); db_session.flush()

    calls = []
    def fake_call(session, **kw):
        calls.append(kw)
        return "HOPE\nDESCRIPTION: green marker on paper."
    monkeypatch.setattr(s3_artefacts.router, "call", fake_call)

    rep = s3_artefacts.run(db_session, job.id)
    assert len(calls) == 1 and calls[0]["level"] == 2 and calls[0]["images"] == [pic]
    arts = db_session.query(Artefact).all()
    assert len(arts) == 1 and arts[0].verbatim_text == "HOPE"
    assert any("Level 3" in f.get("skipped", "") for f in rep["files"])
