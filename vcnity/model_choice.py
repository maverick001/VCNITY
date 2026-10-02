"""Which local model each step uses, chosen per job by the analyst.

Only models already on this laptop are offered: speech models in the app's own
cache, text and vision models from Ollama. Nothing hosted is ever listed (PRD
A7, §5). Level 3 still reaches no model at all — that's the router's job, and a
choice made here can't change it. A job with no choice uses the defaults from
app/.env.
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import settings
from .models import Job

DEFAULT_SPEECH = os.environ.get("VCNITY_ASR_MODEL", "large-v3")

# step → (name on screen, kind of model, what it does)
STEPS: dict[int, tuple[str, str, str]] = {
    2: ("Audio processing", "speech", "Turns recordings into text."),
    3: ("Image processing", "vision", "Reads what's written in photos of things people made."),
    4: ("Draft themes", "text", "Finds names to swap in Level 2 material, and names each group of quotes."),
    5: ("Evidence check", "text", "Checks every theme's summary against its quotes."),
    7: ("Security check", "text", "Looks for anything in a theme that could give someone away."),
    8: ("Reporting", "text", "Drafts the findings in the client report."),
}

# 16GB of RAM, no GPU, and the app and database need room too. Above this, warn before it's picked.
MEMORY_WARN_GB = 8.0

# Parameter counts for faster-whisper's models, from OpenAI's Whisper model card and the distil-whisper
# cards. The downloaded files don't say, and the size on disk isn't the same thing.
SPEECH_PARAMS = {
    "tiny": "0.04B", "base": "0.07B", "small": "0.24B", "medium": "0.77B",
    "large-v1": "1.55B", "large-v2": "1.55B", "large-v3": "1.55B", "large": "1.55B",
    "large-v3-turbo": "0.81B", "turbo": "0.81B",
    "distil-small.en": "0.17B", "distil-medium.en": "0.39B", "distil-large-v2": "0.76B",
    "distil-large-v3": "0.76B", "distil-large-v3.5": "0.76B",
}


def display_name(kind: str, name: str) -> str:
    """What the analyst sees. faster-whisper knows its models by short names ("large-v3"); show the full one."""
    return f"faster-whisper-{name}" if kind == "speech" and not name.startswith("faster-whisper-") else name


def _params_b(text: str | None) -> str:
    """Ollama's parameter size ("4.7B", "809M") in billions, so every model reads the same way."""
    text = (text or "").strip().upper()
    if text.endswith("M"):
        try:
            return f"{float(text[:-1]) / 1000:.2f}B"
        except ValueError:
            return ""
    return text if text.endswith("B") else ""


def default_for(stage: int) -> str:
    kind = STEPS.get(stage, ("", "text", ""))[1]
    return {"speech": DEFAULT_SPEECH, "vision": settings.ollama_vision_model}.get(kind, settings.ollama_model)


def chosen(session, job_id: int, stage: int) -> str:
    """The model a stage should use for this job. Stages without a choice (the chat, report-back) get the default."""
    job = session.get(Job, job_id) if session is not None else None
    picked = (job.models or {}).get(str(stage)) if job is not None and stage in STEPS else None
    return picked or default_for(stage)


def _folder_gb(path: Path) -> float:
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9, 1)


def speech_models() -> list[dict]:
    """faster-whisper models already downloaded into the app's cache (stage 2 downloads them there)."""
    from faster_whisper.utils import _MODELS  # name → Hugging Face repo

    cache = settings.cache_dir / "models"
    out, seen = [], set()
    for name, repo in _MODELS.items():  # some repos go by two names ("turbo", "large-v3-turbo"): list it once
        folder = cache / f"models--{repo.replace('/', '--')}"
        if repo not in seen and any(folder.glob("snapshots/*/model.bin")):
            seen.add(repo)
            out.append({"name": name, "display": display_name("speech", name), "size_gb": _folder_gb(folder),
                        "source": repo.split("/")[0], "params": SPEECH_PARAMS.get(name.removesuffix(".en"), "")})
    return out


def ollama_models() -> tuple[list[dict], list[dict], str]:
    """(text models, vision models, error). Ollama decides what each model can do."""
    try:
        import ollama

        client = ollama.Client()
        text, vision = [], []
        for m in client.list().models:
            info = client.show(m.model)
            caps = list(getattr(info, "capabilities", None) or [])
            row = {"name": m.model, "display": m.model, "size_gb": round((m.size or 0) / 1e9, 1), "source": "Ollama",
                   "params": _params_b(getattr(getattr(info, "details", None), "parameter_size", None))}
            if "vision" in caps:
                vision.append(row)
            if "completion" in caps:
                text.append(row)
        return text, vision, ""
    except Exception as e:  # noqa: BLE001 — Ollama not running is a normal state to report, not a crash
        return [], [], f"Ollama isn't answering ({type(e).__name__}). Start it to see its models."


def available() -> dict:
    text, vision, error = ollama_models()
    try:
        speech = speech_models()
    except Exception:  # noqa: BLE001
        speech = []
    return {"speech": speech, "vision": vision, "text": text, "ollama_error": error}


def set_choices(session, job_id: int, choices: dict) -> dict:
    """Save the analyst's picks. Each must be a step we offer and a model on this laptop for that kind."""
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    have = available()
    current = dict(job.models or {})
    for stage_text, model in choices.items():
        stage = int(stage_text)
        if stage not in STEPS:
            raise ValueError(f"step {stage} has no model to choose")
        kind = STEPS[stage][1]
        if model not in {m["name"] for m in have[kind]}:
            raise ValueError(f"'{model}' isn't a {kind} model on this laptop")
        current[str(stage)] = model
    job.models = current
    session.flush()
    return current
