"""Local model through Ollama. Runs on this machine; nothing leaves it."""
from __future__ import annotations

from pathlib import Path

from .base import Provider


class OllamaProvider(Provider):
    is_local = True

    def __init__(self, model: str, host: str | None = None):
        self.model = model
        self.name = f"ollama:{model}"
        self._host = host

    def complete(self, prompt, system="", images=None, json_mode=False, max_tokens=2000) -> str:
        import ollama

        client = ollama.Client(host=self._host) if self._host else ollama.Client()
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
