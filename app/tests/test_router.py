from dataclasses import replace

import pytest

from vcnity.models import AICall
from vcnity.providers import router
from vcnity.providers.base import Provider


class Fake(Provider):
    name = "fake"
    is_local = True
    model = "fake-model"

    def complete(self, prompt, system="", images=None, json_mode=False, max_tokens=2000):
        return "ok"


def test_level3_never_reaches_a_provider(db_session, monkeypatch):
    monkeypatch.setattr(router, "_local", lambda model=None: Fake())
    with pytest.raises(router.Level3NoAI):
        router.call(db_session, job_id=1, stage=4, level=3, purpose="t", prompt="x", redacted=True)
    assert db_session.query(AICall).count() == 0


def test_level2_requires_redacted(db_session, monkeypatch):
    monkeypatch.setattr(router, "_local", lambda model=None: Fake())
    with pytest.raises(router.UnredactedLevel2):
        router.call(db_session, job_id=1, stage=4, level=2, purpose="t", prompt="x", redacted=False)
    assert db_session.query(AICall).count() == 0
    out = router.call(db_session, job_id=1, stage=4, level=2, purpose="t", prompt="x", redacted=True)
    assert out == "ok"
    row = db_session.query(AICall).one()
    assert row.is_local is True and row.level == 2 and row.provider == "fake"


def test_level1_local_by_default(db_session, monkeypatch):
    monkeypatch.setattr(router, "_local", lambda model=None: Fake())
    assert router.call(db_session, job_id=1, stage=4, level=1, purpose="t", prompt="x") == "ok"


def test_hosted_refused_even_when_allowed(db_session, monkeypatch):
    from vcnity.providers.hosted_stub import HostedStub

    with pytest.raises(router.HostedRefused):
        HostedStub().complete("x")
    monkeypatch.setattr(router, "settings", replace(router.settings, allow_hosted=True))
    with pytest.raises(router.HostedRefused):
        router.call(db_session, job_id=1, stage=4, level=1, purpose="t", prompt="x")
    assert db_session.query(AICall).count() == 0


def test_hosted_never_for_level2_even_when_allowed(db_session, monkeypatch):
    monkeypatch.setattr(router, "settings", replace(router.settings, allow_hosted=True))
    monkeypatch.setattr(router, "_local", lambda model=None: Fake())
    assert router.get_provider(2, redacted=True).is_local is True


def test_local_defaults_to_configured_text_model():
    from vcnity.providers.ollama_local import OllamaProvider

    p = router._local()
    assert isinstance(p, OllamaProvider) and p.model == router.settings.ollama_model


def test_local_honours_an_explicit_model_override():
    from vcnity.providers.ollama_local import OllamaProvider

    p = router._local("qwen3-vl:4b")
    assert isinstance(p, OllamaProvider) and p.model == "qwen3-vl:4b"


def test_call_records_the_model_actually_used(db_session, monkeypatch):
    """A caller can ask for a specific model (stage 3 asks for the vision
    model); the audit row must reflect what actually ran, not the default."""
    seen = {}

    class Recording(Provider):
        name = "ollama:qwen3-vl:4b"
        is_local = True
        model = "qwen3-vl:4b"

        def complete(self, prompt, system="", images=None, json_mode=False, max_tokens=2000):
            return "ok"

    def fake_local(model=None):
        seen["model"] = model
        return Recording()

    monkeypatch.setattr(router, "_local", fake_local)
    router.call(db_session, job_id=1, stage=3, level=2, purpose="t", prompt="x",
               redacted=True, model="qwen3-vl:4b")
    assert seen["model"] == "qwen3-vl:4b"
    row = db_session.query(AICall).one()
    assert row.model == "qwen3-vl:4b"
