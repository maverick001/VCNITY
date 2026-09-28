import numpy as np
import pytest

from vcnity import ask
from vcnity.models import Job, Segment, SourceFile


@pytest.fixture(autouse=True)
def fresh_vector_cache(tmp_path, monkeypatch):
    """Each test gets its own embedding cache — fake vectors must never leak into another test."""
    monkeypatch.setattr(ask, "_disk_path", lambda: tmp_path / "ask_vectors.pkl")
    monkeypatch.setattr(ask, "_disk", None)
    ask._vectors.clear()


def _job(db_session, tmp_path):
    job = Job(name="j", status="intake"); db_session.add(job); db_session.flush()
    l1 = SourceFile(job_id=job.id, filename="notes.txt", kind="text", level=1, path="x", sha256="a" * 64)
    l2 = SourceFile(job_id=job.id, filename="rec.m4a", kind="audio", level=2, path="y", sha256="b" * 64)
    l3 = SourceFile(job_id=job.id, filename="secret.m4a", kind="audio", level=3, path="z", sha256="c" * 64)
    db_session.add_all([l1, l2, l3]); db_session.flush()
    notes = tmp_path / "notes.txt"
    notes.write_text("The carpark lights have been broken for months now\n", encoding="utf-8")
    l1.provenance = {"ingested_path": str(notes)}
    db_session.add_all([
        Segment(file_id=l2.id, variant="with_wordlist", start_s=75, end_s=80, speaker="SPEAKER_01",
                text="Priya says the bus stop near the park floods every winter"),
        Segment(file_id=l3.id, variant="with_wordlist", start_s=0, end_s=5, speaker="S9",
                text="This is restricted cultural knowledge that must never be read"),
    ])
    db_session.flush()
    return job


def _one_hot(texts):
    # "carpark" texts on axis 0, "bus" texts on axis 1, anything else on axis 2
    return np.array([[1.0, 0, 0] if "carpark" in t.lower() else [0, 1.0, 0] if "bus" in t.lower() else [0, 0, 1.0]
                     for t in texts])


def test_passages_skip_level3_and_swap_level2_names(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "person_names", lambda _p: ["Priya"])
    job = _job(db_session, tmp_path)
    ps = ask.passages(db_session, job.id)
    assert [p["file"] for p in ps] == ["notes.txt", "rec.m4a"]          # nothing from Level 3
    seg = ps[1]
    assert "Priya" in seg["text"] and "Priya" not in seg["model_text"] and "Alex" in seg["model_text"]
    assert seg["where"] == "1:15, SPEAKER_01" and ps[0]["where"] == "paragraph 1"


def test_answer_cites_real_passages_only(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "person_names", lambda _p: ["Priya"])
    monkeypatch.setattr(ask.s4_themes, "embed", _one_hot)
    ask._vectors.clear()
    job = _job(db_session, tmp_path)
    seen = {}

    def fake_call(session, **kw):
        seen.update(kw)
        return "The bus stop floods in winter [S2]. Also something invented [S99]. Both [S1, S99, S2]."
    monkeypatch.setattr(ask.router, "call", fake_call)
    out = ask.ask(db_session, job.id, "bus flooding?", actor_role="analyst")
    assert "S99" not in out["answer"] and "[S2]" in out["answer"] and "[S1, S2]" in out["answer"]
    assert "invented." in out["answer"]                                  # no gap left where [S99] was
    assert [s["id"] for s in out["sources"]] == ["S2", "S1"]
    assert "Priya" in out["sources"][0]["text"]                           # the person sees the original words
    assert seen["redacted"] is True and seen["level"] == 2
    assert "Priya" not in seen["prompt"] and "restricted cultural" not in seen["prompt"]


def test_retrieve_orders_by_closeness(monkeypatch):
    monkeypatch.setattr(ask.s4_themes, "embed", _one_hot)
    ask._vectors.clear()
    items = [{"model_text": t} for t in ("carpark dark", "bus late", "weather")]
    assert [p["model_text"] for p in ask.retrieve("carpark", items, k=1)] == ["carpark dark"]


def test_only_facilitator_and_analyst_may_ask(db_session, tmp_path):
    job = _job(db_session, tmp_path)
    for role in ("community", "client", ""):
        with pytest.raises(PermissionError):
            ask.ask(db_session, job.id, "anything?", actor_role=role)
    with pytest.raises(ask.AskError):
        ask.ask(db_session, job.id, "   ", actor_role="facilitator")


def test_stored_stage4_vectors_are_reused(db_session, tmp_path, monkeypatch):
    job = _job(db_session, tmp_path)
    from vcnity.models import Unit
    f = db_session.query(SourceFile).filter_by(job_id=job.id, level=1).one()
    db_session.add(Unit(job_id=job.id, file_id=f.id, source_type="text", source_id=0,
                        text="The carpark lights have been broken for months now",
                        redacted_text="The carpark lights have been broken for months now", speaker_key="k",
                        level=1, embedding=[0.5] * 768))
    db_session.flush()
    ask._vectors.clear()
    embedded = []
    monkeypatch.setattr(ask.s4_themes, "embed", lambda texts: embedded.extend(texts) or np.zeros((len(texts), 768)))
    ask.retrieve("q", ask.passages(db_session, job.id))
    assert "The carpark lights have been broken for months now" not in embedded   # came from stage 4


def test_embeddings_are_kept_on_disk(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ask.s4_themes, "embed", lambda texts: calls.append(list(texts)) or _one_hot(texts))
    ask.retrieve("carpark", [{"model_text": "carpark dark"}])
    ask._vectors.clear(); ask._disk = None                               # as if the API restarted
    ask.retrieve("carpark", [{"model_text": "carpark dark"}])
    assert [t for c in calls for t in c].count("carpark dark") == 1      # embedded once, read back from disk
