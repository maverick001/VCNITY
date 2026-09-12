# VCNITY 2026 AI Project — PRD Workspace + Prototype

This repo is two things for an IFN735 industry/capstone project: a **Product Requirements Document (PRD)** for VCNITY's 2026 AI project, and a **working prototype** of the pipeline it describes — an AI-assisted analysis pipeline that turns messy Creative Co-Design material (multi-speaker audio, code-switched languages, local slang, photos of handmade artefacts) into policy-ready themes, without letting AI override community authority over meaning.

This README covers both: how to install and run the prototype, and how the PRD side of the repo is organised.

## Prototype app

A runnable proof of concept of the ten-stage pipeline in `PRD/VCNITY_PRD_v0.3.md` §4, on the material in `Data/raw`. Everything runs on one laptop; no material leaves it.

> **Before you run anything, pull these exact models — the app will not work without them:**
> 
> ```
> ollama pull qwen3.5:4b     # required — text: theme labels, evidence checks, reports
> ollama pull qwen3-vl:4b    # required — vision: reading photos of artefacts
> ```
> 
> These exact tags, not a substitute like `qwen2-vl` or a different size — the app looks up these names literally and Ollama will 404 on anything else.

![The prototype's Intake page — every file gets a consent record and a sensitivity level before anything runs on it](Image/index_page.jpg)

### What it proves

| PRD rule                                                                  | Where it is code                                                                               | What to show the client                                                                                                                            |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Level 3 never reaches AI — not "outside AI", *any* model                  | `vcnity/providers/router.py` raises before a provider is chosen; every call logs to `ai_calls` | The audit panel at the top of every page reads **0 · 0**. Raise a photo to Level 3 on the Intake page and watch its quotes vanish from the themes. |
| The community decides meaning                                             | `vcnity/stages/s6_signoff.py` → `AuthorityError` → API 409                                     | As *analyst*, press "Try to confirm (will be refused)" on a community-decided theme.                                                               |
| Every theme traces to a real quote                                        | `vcnity/stages/s4_themes.py` — quotes are cluster members; the model only labels               | Open any theme's quotes. Stage 5 hides anything whose summary says more than its quotes.                                                           |
| Nothing above Level 1 goes near AI until the community confirms the level | `vcnity/pipeline.py` `GateError` → API 409                                                     | Set a file to Level 2 without confirming, then try to run stage 4.                                                                                 |
| Analyst cuts need a written reason                                        | `vcnity/stages/s7_identify.py`                                                                 | Try to cut a flag with an empty reason.                                                                                                            |
| Report leaves only with both approvals                                    | `vcnity/stages/s8_report.py` → 403                                                             | Export is disabled until community *and* analyst approve.                                                                                          |

### Run it

Prerequisites (both Windows 11 and macOS):

1. [uv](https://docs.astral.sh/uv/) on the PATH.
2. [Ollama](https://ollama.com) running, with the two models above pulled. On a 16GB, no-GPU machine the two are never loaded into Ollama at the same time — see `app/vcnity/providers/ollama_local.py` — so this fits as long as pipeline stages keep running one at a time.
3. Optional — speaker labels: a free HuggingFace token with the terms accepted on `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`. Put it in `app/.env` as `HF_TOKEN=hf_…`. Without it, stage 2's transcript still works; segments just come back without a speaker label.

Then:

```
git clone <repo-url> && cd <repo>
cp app/.env.example app/.env        # set VCNITY_DATA_DIR if Data/raw is elsewhere
python app/start.py                  # syncs deps into ~/.vcnity, starts Postgres + API + UI
```

First run downloads ~2 GB of Python packages and, on the first transcription, the 3 GB whisper model. The UI is at http://localhost:3000 .

Nothing heavy is written inside this folder: the venv, the embedded PostgreSQL data, model weights and the Reflex build all live in `~/.vcnity/`. 

### Precompute before the demo

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

### Demo script (about 15 minutes)

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

### Layout

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

### Known limits (say them in the demo)

- Level 2 redaction is regex plus the word list's `@person` names, not a named-entity model.
- The word-list measure needs a human-corrected transcript to be a real WER; until one is pasted in, the page shows what the word list *changed*, not whether it was right.
- The vision model reads big marker text well and guesses small handwriting rather than marking it illegible. The maker statement and community sign-off are the correction.
- Roles are a dropdown. There is no login; this is a proof of concept (PRD A1).
- Tested on Windows 11. The code is cross-platform (pathlib, PyAV, pgserver's macOS binaries) but has not been run on a Mac.

## PRD workspace

### Getting the files

This folder is synced via Google Drive, and also tracked in git so changes can be reviewed as diffs. To get a working copy:

```
git clone <repo-url>
```

Most of the working content (`PRD/`, `Document/`, `Docs/`, `Data/`, `Assessment1/`) is currently **untracked** in git — it lives on disk/Drive but hasn't been committed yet. If you're joining via git alone, ask a teammate to share the Drive folder directly, or check `git status` after cloning to see what's missing locally.

### What's where

- **`PRD/VCNITY_PRD_v0.3.md`** — the live PRD, the working source of truth. `v0.2` sits alongside it as the immediately-prior draft, kept for reference — don't edit it.
- **`app/`** — the prototype app, see **Prototype app** above.
- **`PRD/VCNITY-PRD-Clarification-Questions.md`** — numbered open questions for the product owner, grouped by topic.
- **`Document/VCNITY 2026 AI project.pdf`** — the client's pitch deck. Every requirement in the PRD should trace back to a slide in here.
- **`Document/VCNITY_Technical_Workflow_Proposal_Shafwon.pdf`** — the team's own wider-platform sketch. Not submitted, not committed to — don't treat it as scope.
- **`Document/`** — client correspondence and unit IP terms.
- **`Assessment1/`** — the assessment 1 pitch/proposal deliverables (proposal draft, technical solution sections, pitch deck).
- **`Data/Raw/`** — raw source material for analysis.
- **`Docs/superpowers/`** — implementation-plan records for document revisions (e.g. deck-to-PRD alignment history). Worth reading before a large PRD revision.
- **`CLAUDE.md`** — the authoritative guide to how this repo is organised and how the PRD must be written (voice, scope boundaries, assumption-marker rules). Read this before editing the PRD.

### How to review/verify a change

There's no test command for the PRD. "Verification" here means:

1. **Re-read the PRD** after any edit — check it against the deck (`Document/VCNITY 2026 AI project.pdf`) so every requirement still traces to a slide.
2. **Check the assumption markers.** Every `` `[A1]` ``…`` `[An]` `` inline marker in the PRD must have a matching row in the §9 assumption table, and vice versa. After adding/removing one, renumber and check both directions — `grep -n '\[A[0-9]' PRD/VCNITY_PRD_v0.3.md` is a quick way to list them all.
3. **Check scope stayed pipeline-only.** Community hub, ideas board, public pages, job matching, billing, SROI numbers, engagement analytics, moderation, retention after a job, and AI distress detection are explicitly out of scope — flag anything that creeps toward these.
4. **Preserve the two non-negotiable rules:** when community and analyst disagree about what material *means*, the community decides; and Level 3 sensitivity material reaching an outside AI service is zero, no exceptions. Confirm both survived your edit.
5. **Don't reword/reorder/delete existing sentences as a side effect** of an unrelated change — diff your edit (`git diff`) and make sure unrelated lines didn't move.

### Git conventions

- Current branch: `main`.
- Commits use conventional style scoped to the document, e.g. `docs(prd): trim to the deliverable core`, with a body explaining what was cut/added and why, plus a line-count delta.
- `git log` on the PRD's pre-move history needs the old filename (`VCNITY-2026-AI-PRD-DRAFT.md`) — see `CLAUDE.md` for the full story on the file move.

### Don't touch

- `Archive/` — excluded on purpose (`.claudeignore` / `.gitignore`). Leave it alone unless someone points at a specific file inside it.
- `LEC*/`, `TUT*/` — unit teaching material, not project material.
- `~WRL*.tmp` — Word autosave leftovers, safe to ignore.
