# VCNITY prototype

A runnable proof of concept of the ten-stage pipeline in `PRD/VCNITY_PRD_v0.3.md` §4, on the material in `Data/raw`. Everything runs on one laptop; no material leaves it.

## What it proves

| PRD rule | Where it is code | What to show the client |
|---|---|---|
| Level 3 never reaches AI — not "outside AI", *any* model | `vcnity/providers/router.py` raises before a provider is chosen; every call logs to `ai_calls` | The audit panel at the top of every page reads **0 · 0**. Raise a photo to Level 3 on the Intake page and watch its quotes vanish from the themes. |
| The community decides meaning | `vcnity/stages/s6_signoff.py` → `AuthorityError` → API 409 | As *analyst*, press "Try to confirm (will be refused)" on a community-decided theme. |
| Every theme traces to a real quote | `vcnity/stages/s4_themes.py` — quotes are cluster members; the model only labels | Open any theme's quotes. Stage 5 hides anything whose summary says more than its quotes. |
| Nothing above Level 1 goes near AI until the community confirms the level | `vcnity/pipeline.py` `GateError` → API 409 | Set a file to Level 2 without confirming, then try to run stage 4. |
| Analyst cuts need a written reason | `vcnity/stages/s7_identify.py` | Try to cut a flag with an empty reason. |
| Report leaves only with both approvals | `vcnity/stages/s8_report.py` → 403 | Export is disabled until community *and* analyst approve. |

## Run it

Prerequisites (both Windows 11 and macOS):

1. [uv](https://docs.astral.sh/uv/) on the PATH.
2. [Ollama](https://ollama.com) running, with a vision-capable model pulled: `ollama pull qwen3.5:4b`.
3. Optional — speaker labels: a free HuggingFace token with the terms accepted on `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`. Put it in `app/.env` as `HF_TOKEN=hf_…`.

Then:

```
cp app/.env.example app/.env        # set VCNITY_DATA_DIR if Data/raw is elsewhere
python app/start.py                  # syncs deps into ~/.vcnity, starts Postgres + API + UI
```

First run downloads ~2 GB of Python packages and, on the first transcription, the 3 GB whisper model. The UI is at http://localhost:3000, the API at http://127.0.0.1:8100.

Nothing heavy is written inside this folder: the venv, the embedded PostgreSQL data, model weights and the Reflex build all live in `~/.vcnity/`. That is deliberate — this repo sits in a Google Drive folder.

## Precompute before the demo

Transcription of the two recordings takes about an hour on a laptop CPU. Do it once beforehand:

```
uv run --project app python app/scripts/precompute.py --confirm-levels --demo-signoff
```

That runs stages 1–5, then fills stages 6–9 with clearly labelled demo decisions so every page has content. To hand the sign-off back to real people for the live demo:

```
uv run --project app python app/scripts/precompute.py --job 1 --reset-signoff
```

If the HF token arrives after the precompute, add speaker labels without re-transcribing:

```
uv run --project app python app/scripts/precompute.py --job 1 --stages 2 --only-diarise
```

## Demo script (about 15 minutes)

Switch role with the "I am the" selector at the top right. The stage list on the left shows what is done.

1. **Intake** as *facilitator*. Six files, each with a level and a consent record. Point at the brief — it came from the client's own spreadsheet, exercising the text-input path. Point at "confirmed by community" — nothing above Level 1 ran until that box was ticked.
2. **Transcription.** Two columns: with the community word list and without. Changed words are highlighted. Amber segments are the ones the model was not sure about — those go to a person. Say out loud: far-field, quiet, noisy recordings; 15–30 % word error is realistic; this is why there is a person in the loop.
3. **Things people made.** Verbatim text with spelling kept (`FRENDSHIP`, `Your doing great`), a description of the frame, and an empty "what the maker said it means" box. The AI never fills that box. Say out loud: the photos are 480×360 messaging-app copies; the body-map annotations are guesses — originals would fix it.
4. **Draft themes.** Open a theme's quotes. Every quote is a real unit from the material; the model only wrote the label and summary from them.
5. **Sign-off** as *community*. Confirm one, fix one (change the label), reject one. Then switch to *analyst* and press "Try to confirm" on a community-decided theme — the API refuses with 409.
6. **Could anyone be identified?** as *analyst*. Decide each flag; the reason field is required.
7. **Report.** Council-style: background, how we engaged, a "N of M participants (X %)" table, findings drafted from the table only. Approve as community, then as analyst; only then does Export light up.
8. **Report back.** The plain-language version. Same two approvals.
9. **Live demonstration of authority over data.** Back on Intake, raise one photo to Level 3. Its quotes leave every theme; a theme left with nothing becomes unsupported; the audit panel still reads 0.
10. **Raise a concern** from any page. It lands in Concerns unsorted; as *analyst*, sort it and see where it routes. Harm routes to a safety contact that is deliberately `UNSET` — PRD A13.

## Layout

```
app/
  start.py            launcher (stdlib only)
  vcnity/             the pipeline — no web framework imports
    providers/        router.py is the one door every model call passes through
    stages/           s0_intake … s9_reportback, concerns.py
    pipeline.py       stage runner, gates, raise-to-Level-3 cascade
  api/app.py          Flask; owns the DB; runs stages in a thread
  ui/                 Reflex; pure client of the API
  scripts/precompute.py
  tests/              pytest — 58 tests, no models loaded
```

Tests: `uv run --project app pytest app/tests -q`.

## Known limits (say them in the demo)

- Level 2 redaction is regex plus the word list's `@person` names, not a named-entity model.
- The word-list measure needs a human-corrected transcript to be a real WER; until one is pasted in, the page shows what the word list *changed*, not whether it was right.
- The vision model reads big marker text well and guesses small handwriting rather than marking it illegible. The maker statement and community sign-off are the correction.
- Roles are a dropdown. There is no login; this is a proof of concept (PRD A1).
- Tested on Windows 11. The code is cross-platform (pathlib, PyAV, pgserver's macOS binaries) but has not been run on a Mac.
