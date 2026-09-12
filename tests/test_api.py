import io
import json

import pytest


@pytest.fixture()
def client(pg_uri, monkeypatch):
    from vcnity.providers import router

    monkeypatch.setattr(router, "call", lambda session, **kw: json.dumps({"label": "L", "summary": "S"}))
    from api.app import create_app

    app = create_app(testing=True)
    with app.test_client() as c:
        yield c


def _job(client, name="api job"):
    r = client.post("/jobs", json={"name": name})
    assert r.status_code == 201
    return r.get_json()["id"]


def _upload(client, job_id, name="notes.txt", level=2, body=b"Facilitator notes with more than six words here."):
    r = client.post(f"/jobs/{job_id}/files", data={
        "file": (io.BytesIO(body), name), "level": str(level),
        "consent_label": "c1", "consent_scope": "session"},
        content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_health(client):
    assert client.get("/health").get_json()["ok"] is True


def test_level_only_goes_up(client):
    job = _job(client)
    fid = _upload(client, job, level=2)
    r = client.patch(f"/files/{fid}/level", json={"level": 1, "actor_role": "community"})
    assert r.status_code == 400 and "only go up" in r.get_json()["error"]
    r = client.patch(f"/files/{fid}/level", json={"level": 3, "actor_role": "community"})
    assert r.status_code == 200 and r.get_json()["level"] == 3


def test_gate_then_confirm(client):
    job = _job(client)
    fid = _upload(client, job, level=2)
    r = client.post(f"/jobs/{job}/run/4")
    assert r.status_code == 409 and "confirm" in r.get_json()["error"].lower()
    assert client.post(f"/files/{fid}/confirm").status_code == 200
    r = client.post(f"/jobs/{job}/run/1")
    assert r.status_code == 202


def test_analyst_cannot_override_community(client, pg_uri):
    from vcnity import db
    from vcnity.models import Theme

    job = _job(client)
    with db.session() as s:
        t = Theme(job_id=job, label="x", summary="y", status="draft", level=1)
        s.add(t); s.flush(); tid = t.id
    r = client.patch(f"/themes/{tid}", json={"actor_role": "community", "action": "confirm"})
    assert r.status_code == 200 and r.get_json()["decided_by"] == "community"
    r = client.patch(f"/themes/{tid}", json={"actor_role": "analyst", "action": "fix", "label": "nope"})
    assert r.status_code == 409
    themes = client.get(f"/jobs/{job}/themes").get_json()
    assert themes[0]["label"] == "x"


def test_unsupported_never_listed(client):
    from vcnity import db
    from vcnity.models import Theme

    job = _job(client)
    with db.session() as s:
        s.add(Theme(job_id=job, label="hidden", summary="", status="unsupported", level=1))
        s.add(Theme(job_id=job, label="shown", summary="", status="draft", level=1))
    labels = [t["label"] for t in client.get(f"/jobs/{job}/themes").get_json()]
    assert labels == ["shown"]


def test_flag_decision_needs_reason_and_export_needs_both_approvals(client, tmp_path):
    from vcnity import db
    from vcnity.models import IdentifyFlag, Report, Theme

    job = _job(client)
    with db.session() as s:
        t = Theme(job_id=job, label="x", summary="y", status="confirmed", decided_by="community", level=1, n_people=1)
        s.add(t); s.flush()
        f = IdentifyFlag(theme_id=t.id, kind="small_n", detail="1"); s.add(f); s.flush(); fid = f.id
        rep = Report(job_id=job, kind="client", markdown="# r"); s.add(rep); s.flush(); rid = rep.id
    assert client.post(f"/flags/{fid}/decide", json={"decision": "keep", "reason": ""}).status_code == 400
    assert client.post(f"/flags/{fid}/decide", json={"decision": "keep", "reason": "fine"}).status_code == 200
    assert client.get(f"/reports/{rid}/export").status_code == 403
    client.post(f"/reports/{rid}/approve", json={"actor_role": "community"})
    assert client.get(f"/reports/{rid}/export").status_code == 403
    client.post(f"/reports/{rid}/approve", json={"actor_role": "analyst"})
    r = client.get(f"/reports/{rid}/export")
    assert r.status_code == 200 and r.mimetype.endswith("wordprocessingml.document")


def test_audit_zero(client):
    job = _job(client)
    a = client.get(f"/jobs/{job}/audit").get_json()
    assert a["level3_calls"] == 0 and a["hosted_calls_l2plus"] == 0


def test_concern_flow(client):
    job = _job(client)
    r = client.post(f"/jobs/{job}/concerns", json={"stage": 6, "text": "something is wrong"})
    assert r.status_code == 201
    cid = r.get_json()["id"]
    r = client.post(f"/concerns/{cid}/sort", json={"category": "misuse"})
    assert r.status_code == 200 and r.get_json()["routed_to"].startswith("VCNITY analyst")


def test_wordlist_roundtrip(client, tmp_path, monkeypatch):
    from dataclasses import replace

    from api import app as api_app

    p = tmp_path / "w.txt"
    monkeypatch.setattr(api_app, "settings", replace(api_app.settings, wordlist_path=p))
    assert client.put("/wordlist", json={"text": "Kelvin Grove\nPriya @person\n"}).status_code == 200
    got = client.get("/wordlist").get_json()
    assert got["words"] == ["Kelvin Grove", "Priya"] and got["persons"] == ["Priya"]
