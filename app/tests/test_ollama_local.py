"""This laptop has 16GB RAM and no GPU. Two Ollama models (text + vision) are
in play across the pipeline, and they must never be resident at once — see
vcnity/providers/ollama_local.py. These tests exercise the swap guard without
touching a real Ollama server.
"""
from __future__ import annotations

import sys
import types

import pytest


class FakeMessage(dict):
    """Mimics ollama's Message: dict-style access plus a .content attribute,
    since OllamaProvider.complete reads resp["message"]["content"]."""


class FakeClient:
    """Records every chat()/generate() call so tests can assert on ordering."""

    def __init__(self, *a, **kw):
        self.calls: list[tuple[str, dict]] = []

    def chat(self, **kwargs):
        self.calls.append(("chat", kwargs))
        return {"message": {"content": "ok"}}

    def generate(self, **kwargs):
        self.calls.append(("generate", kwargs))
        return {"response": ""}


@pytest.fixture()
def fake_ollama(monkeypatch):
    from vcnity.providers import ollama_local

    monkeypatch.setattr(ollama_local, "_loaded_model", None, raising=False)
    client = FakeClient()
    fake_module = types.SimpleNamespace(Client=lambda *a, **kw: client)
    monkeypatch.setitem(sys.modules, "ollama", fake_module)
    return client


def _provider(model):
    from vcnity.providers.ollama_local import OllamaProvider

    return OllamaProvider(model)


def test_first_call_loads_with_no_prior_unload(fake_ollama):
    _provider("qwen3.5:4b").complete("hi")
    kinds = [c[0] for c in fake_ollama.calls]
    assert kinds == ["chat"]  # nothing to unload yet


def test_same_model_twice_never_unloads(fake_ollama):
    _provider("qwen3.5:4b").complete("hi")
    _provider("qwen3.5:4b").complete("again")
    kinds = [c[0] for c in fake_ollama.calls]
    assert kinds == ["chat", "chat"]  # stayed warm, no wasted reload


def test_switching_model_unloads_the_previous_one_first(fake_ollama):
    _provider("qwen3.5:4b").complete("hi")
    _provider("qwen3-vl:4b").complete("read this photo")
    kinds_and_models = [(kind, kw.get("model")) for kind, kw in fake_ollama.calls]
    assert kinds_and_models == [
        ("chat", "qwen3.5:4b"),
        ("generate", "qwen3.5:4b"),  # unload the old model...
        ("chat", "qwen3-vl:4b"),     # ...before the new one loads
    ]
    # the unload call must not linger (keep_alive=0), not just skip a prompt
    unload_call = fake_ollama.calls[1][1]
    assert unload_call.get("keep_alive") == 0


def test_switching_back_and_forth_unloads_each_time(fake_ollama):
    _provider("qwen3.5:4b").complete("a")
    _provider("qwen3-vl:4b").complete("b")
    _provider("qwen3.5:4b").complete("c")
    kinds = [c[0] for c in fake_ollama.calls]
    assert kinds == ["chat", "generate", "chat", "generate", "chat"]


def test_unload_failure_does_not_break_the_real_call(fake_ollama, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("ollama server hiccup")

    _provider("qwen3.5:4b").complete("a")
    fake_ollama.generate = boom
    out = _provider("qwen3-vl:4b").complete("b")
    assert out == "ok"  # the chat call still succeeds even though unload errored
