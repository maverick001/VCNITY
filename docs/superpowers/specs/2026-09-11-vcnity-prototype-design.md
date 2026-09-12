# VCNITY prototype — design

**Date:** 2026-09-11 · **Status:** approved in chat (stack, demo mode, diarisation, reporting scope) · **Spec for:** `PRD/VCNITY_PRD_v0.3.md` §4 pipeline

## Why

The PRD describes a ten-stage pipeline. The client has never seen it move. This prototype exists to walk the product owner through every stage on real material — two recordings and three artefact photos from `Data/raw` — so each open assumption in the PRD can be answered by pointing at a screen rather than a paragraph. It is a proof of concept (PRD A1): it holds demo data on one laptop and is never live with community data.

## What it must show

1. Every one of the ten stages in PRD §4, in order, with the human step visible wherever the table says a person acts.
2. **The community decides meaning.** A community reviewer's confirm / fix / reject / add on a theme cannot be overridden by the analyst. The only thing an analyst can do to a community-confirmed theme is cut it at stage 7 for identifiability, with a written reason.
3. **Level 3 never reaches AI.** Not "outside AI" — *any* model, local or hosted. Enforced in one function every AI call passes through, and counted in an audit log the UI shows.
4. Transcription with the community word list beside transcription without it (PRD §5, the headline research measure).
5. Every draft theme linked to the verbatim quotes it came from; themes with no quotes never reach a reviewer.
6. A client report in the client's own genre (Shape Your Ipswich): a Theme | N of M (X%) table plus a findings narrative, gated on both community and analyst approval.
7. A plain-language report-back for participants.
8. A "raise a concern" form reachable from any stage, sorted by a person.
9. Text inputs (docx / pptx / txt) enter at stage 1 and reach stage 4 without a transcription or image step. The demo uses the client's `Reporting_examples.xlsx` Background paragraphs as the job brief.

## Stack (decided by the user, matches `PRD/TechStack.xlsx`)

| Layer | Choice | Note |
|---|---|---|
| UI | Reflex 0.9 | Pure client of the Flask API. No DB access. |
| API | Flask | Owns the DB and runs pipeline stages in a background thread. |
| DB | PostgreSQL + pgvector via `pgserver` | Embedded — no install on the demo laptop. Verified on Win11; `pgserver` ships macOS binaries. |
| ASR | faster-whisper `large-v3` int8 | Run twice per file: with and without the word list (`hotwords` + `initial_prompt`). |
| Diarisation | pyannote `speaker-diarization-3.1` | Needs `HF_TOKEN`. Runs last; the pipeline works without it (segments unlabelled). |
| Vision + LLM | `qwen3.5:4b` via Ollama | One local model for image description, theme labels, report drafts, and the grounding check. |
| Embeddings + clustering | sentence-transformers `paraphrase-multilingual-mpnet-base-v2` + BERTopic | Falls back to agglomerative clustering (sklearn) if BERTopic's HDBSCAN misbehaves on ~300 units. |
| Env | Python 3.12 via `uv`; venv and Reflex `.web` relocated to `~/.vcnity/` | Keeps thousands of package files out of the Google Drive sync. |

Two Python processes (Flask :8100, Reflex :3000/:8000) plus embedded Postgres. One launcher (`app/start.py`, stdlib only) starts all three on Windows and macOS.

## Layout

```
app/
  start.py               launcher: sets env, uv sync, starts pg + flask + reflex
  pyproject.toml         uv project
  .env.example           HF_TOKEN, OLLAMA_MODEL, VCNITY_DATA_DIR
  vcnity/                pipeline package — no web framework imports
    config.py            paths, model names, env
    db.py                pgserver bootstrap, SQLAlchemy engine/session
    models.py            ORM (below)
    providers/           base.py · ollama_local.py · hosted_stub.py · router.py
    stages/              s0_intake … s9_reportback, one module each
    redact.py            Level 2 redaction before any model call
    wordlist.py          community word list load/merge
    pipeline.py          run_stage(job, n), cache check, status
    audit.py             one row per AI call
  api/app.py             Flask endpoints
  ui/                    Reflex app (rxconfig.py, ui/ui.py, ui/pages/*)
  tests/                 pytest — providers/router, redact, evidence, signoff authority, ingest
  scripts/precompute.py  full run on Data/raw; writes cache + DB
  data/wordlist.txt      seed community word list (editable in UI)
```

## Data model

`jobs` (id, name, brief, status) · `consent_records` (job, participant_label, granted, scope) · `source_files` (job, filename, kind ∈ audio|image|text, level ∈ 1|2|3, level_confirmed_by_community, consent_id, sha256, path, provenance) · `segments` (file, start_s, end_s, speaker, text, confidence, variant ∈ with_wordlist|without) · `artefacts` (file, description, verbatim_text, illegible_count, maker_statement) · `units` (job, source_type, source_id, text, redacted_text, speaker_key, embedding vector(768), excluded) · `themes` (job, label, summary, status ∈ draft|unsupported|confirmed|fixed|rejected|added|cut, decided_by ∈ community|analyst|null, n_people) · `theme_quotes` (theme, unit) · `reviews` (theme, actor_role, action, before, after, note) · `identify_flags` (theme, kind ∈ small_n|pii, detail, decision, reason) · `reports` (job, kind ∈ client|reportback, markdown, approved_community, approved_analyst) · `concerns` (job, stage, text, category, routed_to, level, status) · `ai_calls` (job, stage, provider, is_local, level, model, purpose).

The `with_wordlist` variant is canonical; `without` exists only for the §5 comparison.

## The rules, as code

**Router** (`providers/router.py`): `get_provider(level, purpose)`. Level 3 → raises `Level3NoAI` before any provider is chosen. Level 2 → local providers only, and the caller must pass `redacted_text`, never `text`. Level 1 → local by default; hosted only if `VCNITY_ALLOW_HOSTED=1` *and* a hosted provider is configured (it is not — `hosted_stub` refuses every call and logs the attempt). Every successful call writes an `ai_calls` row. The UI's benchmark panel shows `count(ai_calls where level=3)` and `count(where is_local=false and level>=2)`; both must read 0.

**Level confirmation** (A4): `run_stage` refuses stages 2–5 and 8–9 for any file with `level > 1 and not level_confirmed_by_community`. The facilitator sets the level at intake; a community reviewer confirms it on the intake page. Raising a level is always allowed; lowering is refused by the API.

**Raising to Level 3 after AI has run**: all `units` derived from that file get `excluded = true`; every theme loses those quotes; a theme left with fewer than one quote becomes `unsupported`. This is the "community can raise it any time" demo.

**Community authority** (stage 6): `PATCH /themes/{id}` with `actor_role=analyst` on a theme whose `decided_by == community` returns 409. The only analyst path after that is stage 7's `cut`, which requires a non-empty `reason`.

**Evidence check** (stage 5): quotes come from cluster membership, so a theme cannot cite text that does not exist. The check then (a) verifies every `theme_quotes.unit` still exists and is not excluded, (b) asks the local model whether the summary makes any claim the quotes do not support, with a strict yes/no-plus-sentence prompt, and (c) marks the theme `unsupported` on (a) failing or (b) answering yes. Unsupported themes are never listed on the sign-off page. Benchmark: unsupported themes that reach a reviewer / total = 0 by construction; the UI reports it anyway.

**Identifiability** (stage 7): `small_n` when distinct `speaker_key` behind a theme < 3 (A6, the number is a config value); `pii` on regex (phone, email, street address) plus a local-model scan for names and identifying detail in the quotes. Each flag needs an analyst decision (`keep` | `cut`) and a reason before stage 8 will run.

**Report** (stage 8): themes with status ∈ {confirmed, fixed, added} and no `cut`. Table rows are `label | N of M participants (X%) — summary`, where M = distinct `speaker_key` across included units. Findings narrative drafted by the local model *from the table only*, against the brief. Export blocked until `approved_community and approved_analyst`. Output: Markdown and `.docx`.

**Report back** (stage 9): local model rewrites the report's table and findings at a plain reading level, second person to participants. Same dual approval. "Send" marks it sent; nothing is actually transmitted.

**Concerns**: form fields are `text` and `stage`; category is set by a person afterwards from {harm, misuse, conduct, ai_error} and routing follows the PRD 6.1 table (harm → named safety contact, Level 3; misuse → analyst, Level 2; conduct → community org cc VCNITY, Level 2; ai_error → analyst, level of the material). The named safety contact is a config value that defaults to `UNSET — see PRD A16`.

## Stage behaviour on the demo data

| Stage | Input | What happens | Output shown |
|---|---|---|---|
| 0 Intake | 5 files + xlsx | Facilitator picks level per file, links a consent record. Defaults: recordings L2, photos L2 (unsure → higher). | Table with level, consent, confirmation checkbox |
| 1 Ingest | files | Audio → 16 kHz mono wav (PyAV). Images → sha256 + EXIF strip. xlsx → brief text. docx/pptx/txt → text (no sample in `Data/raw`; path is tested with a fixture). | Provenance record per file |
| 2 Transcription | wav | faster-whisper large-v3, int8, VAD on, `condition_on_previous_text=False`, run with and without word list. Segments with avg logprob below a threshold flagged "not sure — needs a person". | Two transcripts side by side, diff highlighted, flagged segments |
| 2b Diarisation | wav | pyannote 3.1 if `HF_TOKEN` set; speaker labels merged onto segments by overlap. | Speaker column |
| 3 Things people made | images | Local VLM, verbatim transcription with `[illegible]` markers, no spelling correction, plus a description of *what is in the frame*. Prompt forbids interpretation. `maker_statement` is a free-text field a person fills in. | Photo, verbatim text, description, empty maker statement |
| 4 Draft themes | units | Embed (`redacted_text` for L2), cluster, local model labels each cluster from its quotes only. | Theme cards with quotes |
| 5 Evidence check | themes | Structural + grounding check. | Unsupported count; those themes hidden |
| 6 Sign-off | themes | Community reviewer: confirm / fix (edit label+summary) / reject / add. Decisions lock. | Status per theme, review log |
| 7 Identified? | themes | small_n + pii flags; analyst keep/cut with reason. | Flags, decisions, reasons |
| 8 Report | themes | Council-style Markdown; dual approval; export. | Rendered report, approval toggles, download |
| 9 Report back | report | Plain-language version; dual approval; "send". | Rendered text |

Precompute: `scripts/precompute.py` runs 0–9 once (≈2 h on this laptop, dominated by ASR ×2 and diarisation) and stores everything in Postgres. The UI reads from the DB; every stage card has a **Re-run** button that calls the API, which re-executes that stage live and overwrites.

## Word list

`data/wordlist.txt`, one term per line, editable in the intake page. Seed: place names and terms known from the material (Kelvin Grove, QUT, Ipswich, Tulmur, Meanjin, FQI). The §5 measure needs a human-corrected reference transcript to compute a real WER; the prototype shows the with/without diff and the jiwer distance *between the two runs*, labelled as "how much the word list changed", not accuracy, and provides a text box to paste a reference for one file so a real WER can be shown on demand.

## Testing

pytest on the `vcnity` package only, no models loaded: router refuses L3 and unredacted L2; redactor strips phone/email/listed names; evidence check drops a theme whose quote was excluded; sign-off returns 409 on analyst override; ingest handles docx/pptx/txt fixtures; report excludes rejected and cut themes and blocks export without both approvals. Model-dependent stages are exercised by `precompute.py` against `Data/raw` and checked by reading the output.

## Out of scope for the prototype

Real authentication (roles are a dropdown), hosting (Vercel/Aiven rows in TechStack are for later), MySQL backup DB, real WER without a reference transcript, distress detection, moderation, anything in the PRD's Out list.

## Known limits to say out loud in the demo

- The three photos are 480×360 messaging-app copies; small handwriting is unrecoverable and the VLM will mark it `[illegible]`. Originals fix this.
- The recordings are far-field, low volume, noisy; expect 15–30% word error and rough speaker boundaries. The "needs a person" flags are the honest answer to that.
- Level 2 redaction is regex plus the word list, not a named-entity model.
