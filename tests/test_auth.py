import io

import pytest


@pytest.fixture()
def client(pg_uri):
    from api.app import create_app

    app = create_app(testing=True, auth_on=True)
    with app.test_client() as c:
        yield c


def _users(names_roles):
    """Make accounts straight in the database, the way scripts/users.py does."""
    from vcnity import auth, db
    from vcnity.models import Job

    with db.session() as s:
        jobs = [Job(name="auth job A"), Job(name="auth job B")]
        s.add_all(jobs)
        s.flush()
        ids = [j.id for j in jobs]
        for name, role, job in names_roles:
            auth.create_user(s, name, "password123", role, ids[job] if job is not None else None)
    return ids


def _sign_in(client, name):
    r = client.post("/auth/login", json={"username": name, "password": "password123"})
    assert r.status_code == 200, r.get_json()
    return {"Authorization": f"Bearer {r.get_json()['token']}"}


def test_nothing_without_signing_in(client):
    assert client.get("/health").status_code == 200
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"Authorization": "Bearer forged"}).status_code == 401


def test_wrong_password(client):
    _users([("fac1", "facilitator", None)])
    r = client.post("/auth/login", json={"username": "fac1", "password": "nope-nope"})
    assert r.status_code == 401


def test_role_comes_from_the_account_not_the_body(client):
    ids = _users([("com1", "community", 0), ("cli1", "client", 0)])
    cli = _sign_in(client, "cli1")
    assert client.get(f"/jobs/{ids[0]}/segments", headers=cli).status_code == 403
    assert client.post(f"/jobs/{ids[0]}/run/1", headers=cli).status_code == 403
    com = _sign_in(client, "com1")
    assert client.post(f"/jobs/{ids[0]}/reset", headers=com).status_code == 403
    assert client.get("/auth/me", headers=com).get_json()["role"] == "community"


def test_community_and_client_see_only_their_job(client):
    ids = _users([("com2", "community", 0), ("ana2", "analyst", None)])
    com = _sign_in(client, "com2")
    assert [j["id"] for j in client.get("/jobs", headers=com).get_json()] == [ids[0]]
    assert client.get(f"/jobs/{ids[1]}", headers=com).status_code == 403
    ana = _sign_in(client, "ana2")
    seen = {j["id"] for j in client.get("/jobs", headers=ana).get_json()}
    assert {ids[0], ids[1]} <= seen


def test_client_sees_the_report_only_once_both_approve(client):
    from vcnity import db
    from vcnity.models import Report

    ids = _users([("cli3", "client", 0)])
    with db.session() as s:
        rep = Report(job_id=ids[0], kind="client", markdown="# Report")
        s.add(rep)
        s.flush()
        rid = rep.id
    cli = _sign_in(client, "cli3")
    assert client.get(f"/jobs/{ids[0]}/reports", headers=cli).get_json() == []
    with db.session() as s:
        r = s.get(Report, rid)
        r.approved_community = r.approved_analyst = True
    assert [r["id"] for r in client.get(f"/jobs/{ids[0]}/reports", headers=cli).get_json()] == [rid]


def test_links_carry_the_token(client):
    ids = _users([("fac4", "facilitator", None)])
    fac = _sign_in(client, "fac4")
    r = client.post(f"/jobs/{ids[0]}/files", headers=fac, data={
        "file": (io.BytesIO(b"Some notes from the session."), "n.txt"), "level": "1", "consent_label": "c1"},
        content_type="multipart/form-data")
    assert r.status_code == 201
    fid = r.get_json()["id"]
    token = fac["Authorization"].removeprefix("Bearer ")
    assert client.get(f"/files/{fid}/media").status_code == 401
    assert client.get(f"/files/{fid}/media?t={token}").status_code == 200

def test_only_the_analyst_runs_the_pipeline(client):
    # PRD §3: the facilitator uploads, sets levels and enters attendance, and does no analyst work.
    ids = _users([("fac5", "facilitator", None), ("ana5", "analyst", None)])
    fac = _sign_in(client, "fac5")
    for method, path in [("post", f"/jobs/{ids[0]}/run/1"), ("post", f"/jobs/{ids[0]}/reset"),
                         ("get", f"/jobs/{ids[0]}/names"), ("get", f"/jobs/{ids[0]}/flags"),
                         ("get", f"/jobs/{ids[0]}/themes/unsupported")]:
        assert getattr(client, method)(path, headers=fac).status_code == 403, path
    assert client.get(f"/jobs/{ids[0]}/status", headers=fac).status_code == 200
    ana = _sign_in(client, "ana5")
    assert client.post(f"/jobs/{ids[0]}/reset", headers=ana).status_code == 200


def test_facilitator_sees_only_stages_1_and_2(client):
    from vcnity import db
    from vcnity.models import Theme

    ids = _users([("fac6", "facilitator", None), ("ana6", "analyst", None)])
    job = ids[0]
    with db.session() as s:
        s.add_all([Theme(job_id=job, label="agreed", summary="s", status="confirmed", agreed_upfront=True, level=1),
                   Theme(job_id=job, label="drafted", summary="s", status="draft", level=1)])
    fac, ana = _sign_in(client, "fac6"), _sign_in(client, "ana6")

    # Stages 3-8: refused for the facilitator, still there for the analyst.
    for path in (f"/jobs/{job}/artefacts", f"/jobs/{job}/units", f"/jobs/{job}/audit", f"/jobs/{job}/reports"):
        assert client.get(path, headers=fac).status_code == 403, path
        assert client.get(path, headers=ana).status_code == 200, path
    assert client.post(f"/jobs/{job}/run/3", headers=fac).status_code == 403

    # Stages 1 and 2: still theirs.
    assert client.get(f"/jobs/{job}", headers=fac).status_code == 200
    assert client.get(f"/jobs/{job}/segments", headers=fac).status_code == 200
    assert client.get("/wordlist", headers=fac).status_code == 200

    # Status shows only those two stages, and none of the later stages' counts.
    st = client.get(f"/jobs/{job}/status", headers=fac).get_json()
    assert [x["n"] for x in st["stages"]] == [1, 2]
    assert not {"themes", "units", "open_flags", "uncounted", "waiting_names", "status"} & set(st)
    assert [x["n"] for x in client.get(f"/jobs/{job}/status", headers=ana).get_json()["stages"]] == list(range(1, 10))

    # Themes: only the ones agreed up front, which the Data Ingest page lists.
    assert [t["label"] for t in client.get(f"/jobs/{job}/themes", headers=fac).get_json()] == ["agreed"]
    assert {t["label"] for t in client.get(f"/jobs/{job}/themes", headers=ana).get_json()} == {"agreed", "drafted"}
