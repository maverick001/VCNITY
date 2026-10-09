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
DEFAULT_DIARISE = os.environ.get("VCNITY_DIARISE_MODEL", "pyannote/speaker-diarization-3.1")

# Speaker diarization is a second choice inside step 2: a different model from the one that writes the words, run by
# stage 2b. It is saved in the same jobs.models under its own key, and chosen on the same page.
DIARISE_KEY = "2b"
DIARISE_STEP = ("Speaker Diarization", "diarise", "Works out which voice is which. Doesn't change the words.")
# Each speaker model and the Hugging Face files it needs on this laptop (3.1 borrows two other repos' weights).
DIARISE_MODELS: dict[str, list[tuple[str, str]]] = {
    "pyannote/speaker-diarization-3.1": [
        ("pyannote/speaker-diarization-3.1", "config.yaml"),
        ("pyannote/segmentation-3.0", "pytorch_model.bin"),
        ("pyannote/wespeaker-voxceleb-resnet34-LM", "pytorch_model.bin"),
    ],
    "pyannote/speaker-diarization-community-1": [
        ("pyannote/speaker-diarization-community-1", "config.yaml"),
        ("pyannote/speaker-diarization-community-1", "segmentation/pytorch_model.bin"),
        ("pyannote/speaker-diarization-community-1", "embedding/pytorch_model.bin"),
        ("pyannote/speaker-diarization-community-1", "plda/plda.npz"),
    ],
}

# step → (name on screen, kind of model, what it does)
STEPS: dict[int, tuple[str, str, str]] = {
    2: ("Audio Processing", "speech", "Turns recordings into text."),
    3: ("Image Processing", "vision", "Reads what's written in photos of things people made."),
    4: ("Draft Themes", "text", "Finds names to swap in Level 2 material, and names each group of quotes."),
    5: ("Evidence Check", "text", "Checks every theme's summary against its quotes."),
    7: ("Security Check", "text", "Looks for anything in a theme that could give someone away."),
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
    if kind == "diarise":
        return name.split("/")[-1]
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


def default_for(stage: int | str) -> str:
    if str(stage) == DIARISE_KEY:
        return DEFAULT_DIARISE
    kind = STEPS.get(stage, ("", "text", ""))[1]
    return {"speech": DEFAULT_SPEECH, "vision": settings.ollama_vision_model}.get(kind, settings.ollama_model)


def chosen(session, job_id: int, stage: int) -> str:
    """The model a stage should use for this job. Stages without a choice (the chat, report-back) get the default."""
    job = session.get(Job, job_id) if session is not None else None
    picked = (job.models or {}).get(str(stage)) if job is not None and stage in STEPS else None
    return picked or default_for(stage)


def chosen_diarise(session, job_id: int) -> str:
    """The speaker-detection model for this job (Hugging Face repo name)."""
    job = session.get(Job, job_id) if session is not None else None
    return ((job.models or {}).get(DIARISE_KEY) if job is not None else None) or DEFAULT_DIARISE


def _folder_gb(path: Path, digits: int = 1) -> float:
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e9, digits)


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


def diarise_models() -> list[dict]:
    """Speaker-detection models whose files are all in the Hugging Face cache already (pyannote needs HF_TOKEN once,
    to download; after that it runs fully local)."""
    from huggingface_hub.constants import HF_HUB_CACHE

    cache, out = Path(HF_HUB_CACHE), []
    for name, needs in DIARISE_MODELS.items():
        if all(any((cache / f"models--{repo.replace('/', '--')}").glob(f"snapshots/*/{file}")) for repo, file in needs):
            size = sum(_folder_gb(cache / f"models--{repo.replace('/', '--')}", 3) for repo in {r for r, _ in needs})
            out.append({"name": name, "display": display_name("diarise", name), "size_gb": round(size, 2),
                        "source": name.split("/")[0], "params": ""})
    return out


# What `ollama show` said about each model build (name@digest): its capabilities and parameter size. A build never
# changes, so the /models page asks once per build instead of once per model on every load.
_shown: dict[str, tuple[list[str], str]] = {}


def ollama_models() -> tuple[list[dict], list[dict], str]:
    """(text models, vision models, error). Ollama decides what each model can do."""
    try:
        import ollama

        client = ollama.Client()
        text, vision = [], []
        for m in client.list().models:
            digest = getattr(m, "digest", None)
            key = f"{m.model}@{digest}"
            if not digest or key not in _shown:
                info = client.show(m.model)
                _shown[key] = (list(getattr(info, "capabilities", None) or []),
                               _params_b(getattr(getattr(info, "details", None), "parameter_size", None)))
            caps, params = _shown[key]
            row = {"name": m.model, "display": m.model, "size_gb": round((m.size or 0) / 1e9, 1), "source": "Ollama",
                   "params": params}
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
    try:
        diarise = diarise_models()
    except Exception:  # noqa: BLE001
        diarise = []
    return {"speech": speech, "vision": vision, "text": text, "diarise": diarise, "ollama_error": error}


def set_choices(session, job_id: int, choices: dict) -> dict:
    """Save the analyst's picks. Each must be a step we offer and a model on this laptop for that kind."""
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    have = available()
    current = dict(job.models or {})
    for stage_text, model in choices.items():
        if str(stage_text) == DIARISE_KEY:
            if model not in {m["name"] for m in have.get("diarise", [])}:
                raise ValueError(f"'{model}' isn't a speaker-detection model on this laptop")
            current[DIARISE_KEY] = model
            continue
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
