# VCNITY Prototype

This is a working prototype of an AI-assisted pipeline that turns messy Creative Co-Design material — multi-speaker audio, code-switched languages, local slang, photos of handmade artefacts — into policy-ready themes, without letting AI override the community's say over what things mean. Everything runs on your own laptop; nothing is sent anywhere.

![The prototype's Intake page — every file gets a consent record and a sensitivity level before anything runs on it](Image/index_page.jpg)

## Before you start

Pull these two exact models — the app won't run without them:

```
ollama pull qwen3.5:4b     # text: theme labels, evidence checks, reports
ollama pull qwen3-vl:4b    # vision: reading photos of artefacts
```

Use these exact names. A different tag or size (like `qwen2-vl`) won't work — the app looks them up literally.

You'll also need:

1. [uv](https://docs.astral.sh/uv/) installed and on your PATH.
2. [Ollama](https://ollama.com) running, with the two models above pulled. If your machine has 16GB RAM and no GPU, that's fine — the app never loads both models at once.
3. Optional, for speaker labels in transcripts: a free HuggingFace token (accept the terms on `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`, then add `HF_TOKEN=hf_…` to `app/.env`). Without it, transcription still works, just without speaker labels.

Works on Windows 11 and macOS.

## Install and run

```
git clone <repo-url> && cd <repo>
cp app/.env.example app/.env        # set VCNITY_DATA_DIR if your data isn't in Data/raw
python app/start.py                  # installs dependencies, starts the database, API, and UI
```

Open http://localhost:3000 once it's running.

The first run downloads about 2 GB of Python packages, plus a 3 GB speech-recognition model the first time you transcribe something. None of this is stored in the project folder — it all lives in `~/.vcnity/`, so the repo itself stays small.

## Speeding up transcription

Transcribing a recording can take about an hour on a laptop CPU. If you want it ready ahead of time instead of waiting live, run:

```
uv run --project app python app/scripts/precompute.py --confirm-levels --demo-signoff
```

This processes everything through the theme-drafting stage and fills in the later sign-off steps with placeholder decisions, so every page has something to look at. To clear those placeholders and do sign-off for real:

```
uv run --project app python app/scripts/precompute.py --job 1 --reset-signoff
```

If you add your HuggingFace token after already precomputing, you can add speaker labels without re-transcribing:

```
uv run --project app python app/scripts/precompute.py --job 1 --stages 2 --only-diarise
```

## Using the app

Switch roles with the selector in the top right — the app behaves differently depending on whether you're the facilitator, the community, or the analyst. The stage list on the left shows what's been completed.

The pipeline runs through: **Intake** (upload files, set a sensitivity level and consent) → **Transcription** → **Things people made** (photos and objects) → **Draft themes** → **Sign-off** (community and analyst review) → **Could anyone be identified?** → **Report** → **Report back**. You can also raise a concern from any page.

A couple of things worth knowing while you use it: role selection is just a dropdown (there's no login — this is a proof of concept), and sensitive material never reaches the AI until the community has confirmed its level.
