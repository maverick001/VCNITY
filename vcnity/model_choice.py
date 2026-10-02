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
            out.append({"name": name, "size_gb": _folder_gb(folder)})
    return out


def ollama_models() -> tuple[list[dict], list[dict], str]:
    """(text models, vision models, error). Ollama decides what each model can do."""
    try:
        import ollama

        client = ollama.Client()
        text, vision = [], []
        for m in client.list().models:
            caps = list(getattr(client.show(m.model), "capabilities", None) or [])
            row = {"name": m.model, "size_gb": round((m.size or 0) / 1e9, 1)}
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
