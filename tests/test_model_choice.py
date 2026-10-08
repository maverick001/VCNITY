import pytest

FAKE = {"speech": [{"name": "large-v3", "size_gb": 3.1}, {"name": "large-v3-turbo", "size_gb": 1.6}],
        "vision": [{"name": "qwen3-vl:4b", "size_gb": 3.3}],
        "text": [{"name": "qwen3.5:4b", "size_gb": 3.4}, {"name": "big:70b", "size_gb": 40.0}],
        "diarise": [{"name": "pyannote/speaker-diarization-3.1", "size_gb": 0.03},
                    {"name": "pyannote/speaker-diarization-community-1", "size_gb": 0.03}],
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


def test_who_is_speaking_sits_in_audio_processing_and_defaults_to_3_1(client):
    job = _job(client)
    steps = {s["stage"]: s for s in client.get(f"/jobs/{job}/models").get_json()["steps"]}
    assert set(steps) == {2, 3, 4, 5, 7, 8}          # no extra step: it is a second choice inside step 2
    dz = steps[2]["diarise"]
    assert dz["chosen"] == dz["default"] == "pyannote/speaker-diarization-3.1"
    assert [o["name"] for o in dz["options"]] == ["pyannote/speaker-diarization-3.1",
                                                  "pyannote/speaker-diarization-community-1"]
    assert all("diarise" not in steps[n] for n in steps if n != 2)


def test_a_speaker_model_pick_sticks_to_its_job_and_leaves_the_speech_pick_alone(client):
    job, other = _job(client), _job(client)
    client.put(f"/jobs/{job}/models", json={"models": {"2": "large-v3-turbo"}})
    r = client.put(f"/jobs/{job}/models", json={"models": {"2b": "pyannote/speaker-diarization-community-1"}})
    assert r.status_code == 200
    s2 = {s["stage"]: s for s in client.get(f"/jobs/{job}/models").get_json()["steps"]}[2]
    assert s2["diarise"]["chosen"] == "pyannote/speaker-diarization-community-1" and s2["chosen"] == "large-v3-turbo"
    other2 = {s["stage"]: s for s in client.get(f"/jobs/{other}/models").get_json()["steps"]}[2]
    assert other2["diarise"]["chosen"] == "pyannote/speaker-diarization-3.1"


def test_only_speaker_models_on_this_laptop(client):
    job = _job(client)
    assert client.put(f"/jobs/{job}/models", json={"models": {"2b": "large-v3"}}).status_code == 400
    assert client.put(f"/jobs/{job}/models", json={"models": {"2b": "pyannote/not-downloaded"}}).status_code == 400


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


def test_speaker_models_are_listed_only_when_every_file_is_downloaded(tmp_path, monkeypatch):
    import huggingface_hub.constants as hc
    from vcnity import model_choice

    monkeypatch.setattr(hc, "HF_HUB_CACHE", str(tmp_path))

    def put(repo, file):
        f = tmp_path / f"models--{repo.replace('/', '--')}" / "snapshots" / "abc" / file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")

    assert model_choice.diarise_models() == []
    for repo, file in model_choice.DIARISE_MODELS["pyannote/speaker-diarization-community-1"][:-1]:
        put(repo, file)                                    # one file still missing
    assert model_choice.diarise_models() == []
    put(*model_choice.DIARISE_MODELS["pyannote/speaker-diarization-community-1"][-1])
    assert [m["name"] for m in model_choice.diarise_models()] == ["pyannote/speaker-diarization-community-1"]
    assert model_choice.diarise_models()[0]["display"] == "speaker-diarization-community-1"
