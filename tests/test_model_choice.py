import pytest

FAKE = {"speech": [{"name": "large-v3", "size_gb": 3.1}, {"name": "large-v3-turbo", "size_gb": 1.6}],
        "vision": [{"name": "qwen3-vl:4b", "size_gb": 3.3}],
        "text": [{"name": "qwen3.5:4b", "size_gb": 3.4}, {"name": "big:70b", "size_gb": 40.0}],
        "ollama_error": ""}


@pytest.fixture()
def fake_models(monkeypatch):
    from vcnity import model_choice

    monkeypatch.setattr(model_choice, "available", lambda: FAKE)


@pytest.fixture()
def client(pg_uri, fake_models):
    from api.app import create_app

    with create_app(testing=True).test_client() as c:
        yield c


def _job(client):
    return client.post("/jobs", json={"name": "models job"}).get_json()["id"]


def test_defaults_until_the_analyst_picks(client):
    job = _job(client)
    steps = {s["stage"]: s for s in client.get(f"/jobs/{job}/models").get_json()["steps"]}
    assert set(steps) == {2, 3, 4, 5, 7, 8}
    assert steps[8]["chosen"] == steps[8]["default"]
    assert [o["name"] for o in steps[8]["options"] if o["heavy"]] == ["big:70b"]


def test_a_pick_sticks_to_its_job(client):
    job, other = _job(client), _job(client)
    r = client.put(f"/jobs/{job}/models", json={"models": {"2": "large-v3-turbo", "8": "big:70b"}})
    assert r.status_code == 200
    steps = {s["stage"]: s["chosen"] for s in client.get(f"/jobs/{job}/models").get_json()["steps"]}
    assert steps[2] == "large-v3-turbo" and steps[8] == "big:70b"
    assert {s["stage"]: s["chosen"] for s in client.get(f"/jobs/{other}/models").get_json()["steps"]}[8] != "big:70b"


def test_only_models_on_this_laptop_and_of_the_right_kind(client):
    job = _job(client)
    assert client.put(f"/jobs/{job}/models", json={"models": {"8": "gpt-4o"}}).status_code == 400
    assert client.put(f"/jobs/{job}/models", json={"models": {"3": "qwen3.5:4b"}}).status_code == 400  # not vision
    assert client.put(f"/jobs/{job}/models", json={"models": {"6": "qwen3.5:4b"}}).status_code == 400  # sign-off


def test_router_uses_the_jobs_pick(db_session, fake_models, monkeypatch):
    from vcnity import model_choice
    from vcnity.models import Job
    from vcnity.providers import router

    job = Job(name="router pick")
    db_session.add(job)
    db_session.flush()
    model_choice.set_choices(db_session, job.id, {"5": "big:70b"})
    used = []

    class Fake:
        name, is_local = "fake", True

        def __init__(self, model):
            self.model = model

        def complete(self, *a, **k):
            return "ok"

    monkeypatch.setattr(router, "_local", lambda model=None: used.append(model) or Fake(model))
    router.call(db_session, job_id=job.id, stage=5, level=1, purpose="t", prompt="x")
    router.call(db_session, job_id=job.id, stage=7, level=1, purpose="t", prompt="x")
    assert used == ["big:70b", model_choice.default_for(7)]
    with pytest.raises(router.Level3NoAI):  # a pick never opens Level 3
        router.call(db_session, job_id=job.id, stage=5, level=3, purpose="t", prompt="x")


def test_sizes_read_as_parameters_not_disk():
    from vcnity import model_choice

    assert model_choice._params_b("4.7B") == "4.7B"
    assert model_choice._params_b("809M") == "0.81B"
    assert model_choice._params_b(None) == "" and model_choice._params_b("?") == ""
    assert model_choice.SPEECH_PARAMS["large-v3"] == "1.55B"  # 3.1 GB on disk
    assert model_choice.SPEECH_PARAMS["large-v3-turbo"] == "0.81B"


def test_speech_models_show_their_full_name():
    from vcnity import model_choice

    assert model_choice.display_name("speech", "large-v3") == "faster-whisper-large-v3"
    assert model_choice.display_name("speech", "faster-whisper-large-v3") == "faster-whisper-large-v3"
    assert model_choice.display_name("text", "qwen3.5:4b") == "qwen3.5:4b"


def test_only_the_analyst_sees_or_changes_models(pg_uri, fake_models):
    from api.app import create_app
    from vcnity import auth, db
    from vcnity.models import Job

    with db.session() as s:
        job = Job(name="models auth job")
        s.add(job)
        s.flush()
        jid = job.id
        for name, role in [("mfac", "facilitator"), ("mana", "analyst"), ("mcom", "community")]:
            auth.create_user(s, name, "password123", role, jid)
    with create_app(testing=True, auth_on=True).test_client() as c:
        def headers(name):
            tok = c.post("/auth/login", json={"username": name, "password": "password123"}).get_json()["token"]
            return {"Authorization": f"Bearer {tok}"}

        assert c.get(f"/jobs/{jid}/models", headers=headers("mfac")).status_code == 403
        assert c.get(f"/jobs/{jid}/models", headers=headers("mcom")).status_code == 403
        assert c.get(f"/jobs/{jid}/models", headers=headers("mana")).status_code == 200
        assert c.put(f"/jobs/{jid}/models", headers=headers("mfac"), json={"models": {"8": "big:70b"}}).status_code == 403
