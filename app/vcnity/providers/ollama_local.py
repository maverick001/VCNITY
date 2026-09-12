"""Local model through Ollama. Runs on this machine; nothing leaves it.

Two different models are used at different pipeline stages — qwen3.5:4b for
text (theme labels, evidence checks, reports) and qwen3-vl:4b for reading
photos of artefacts (stage 3). This laptop has 16GB RAM and no GPU, so the two
must never be loaded at once: a 3-4GB model resident twice, or alongside
faster-whisper, risks the OOM kills this project already hit once.

`_ensure_only_one_loaded` is the guard: before any call, if the previously
used model differs from the one about to run, it force-unloads the old one
first (`keep_alive=0`, no prompt — confirmed empirically to evict immediately
via `GET /api/ps`). Calls to the *same* model back-to-back stay warm — only a
genuine switch pays the unload+reload cost.
"""
from __future__ import annotations

from pathlib import Path

from .base import Provider

# Process-wide, not per-instance: OllamaProvider objects are created fresh per
# call (see router._local), so the "what's currently loaded" fact has to live
# above any one instance.
_loaded_model: str | None = None


def _ensure_only_one_loaded(client, model: str) -> None:
    global _loaded_model
    if _loaded_model is not None and _loaded_model != model:
        try:
            client.generate(model=_loaded_model, keep_alive=0)
        except Exception:
            pass  # already gone, or Ollama restarted — either way, fine
    _loaded_model = model


class OllamaProvider(Provider):
    is_local = True

    def __init__(self, model: str, host: str | None = None):
        self.model = model
        self.name = f"ollama:{model}"
        self._host = host

    def complete(self, prompt, system="", images=None, json_mode=False, max_tokens=2000) -> str:
        import ollama

        client = ollama.Client(host=self._host) if self._host else ollama.Client()
        _ensure_only_one_loaded(client, self.model)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        user = {"role": "user", "content": prompt}
        if images:
            user["images"] = [str(Path(p)) for p in images]
        messages.append(user)
        # num_predict caps runaway generation; repeat_penalty discourages the
        # "- -\n- -\n…" loop a vision model falls into on unreadable handwriting.
        options = {"temperature": 0, "num_predict": int(max_tokens), "repeat_penalty": 1.15}
        kwargs = {"model": self.model, "messages": messages, "options": options}
        if json_mode:
            kwargs["format"] = "json"
        try:
            kwargs["think"] = False
            resp = client.chat(**kwargs)
        except TypeError:  # older client without `think`
            kwargs.pop("think", None)
            resp = client.chat(**kwargs)
        return resp["message"]["content"]
