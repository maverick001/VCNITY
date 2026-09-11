# VCNITY Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable demo of the ten-stage PRD §4 pipeline on the five files in `Data/raw`, with the three non-negotiable rules enforced in code.

**Architecture:** A framework-free Python package `vcnity` holds the pipeline, the DB layer and the rules. A Flask API owns the DB and runs stages. A Reflex UI is a pure HTTP client of the API. Embedded PostgreSQL (pgserver) with pgvector needs no install.

**Tech Stack:** Python 3.12 via uv · Reflex 0.9 · Flask 3 · SQLAlchemy 2 + psycopg 3 + pgvector · pgserver · faster-whisper 1.2 · pyannote.audio 4 · sentence-transformers 6 · BERTopic 0.17 · ollama client · python-docx / python-pptx / openpyxl · jiwer · pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-vcnity-prototype-design.md`

## Global Constraints

- Runs on Win11 and macOS from `python app/start.py`; no system Postgres, no Node install beyond what Reflex fetches itself.
- Venv lives at `~/.vcnity/venv` (`UV_PROJECT_ENVIRONMENT`), Reflex web dir at `~/.vcnity/web` (`REFLEX_WEB_WORKDIR`). Nothing heavy inside the Google Drive folder.
- `vcnity/` imports no web framework. `ui/` imports no DB layer. Only `api/` touches both.
- Level 3 → `Level3NoAI` before any provider is chosen. Level 2 → local only, redacted text only. Every model call → one `ai_calls` row.
- Analyst cannot change a theme whose `decided_by == "community"`; 409 at the API, `AuthorityError` in the package.
- Quotes come from cluster membership only. The model never emits a quote.
- All paths through `pathlib`; no shell-specific code; no `os.system`.
- Data dir from `VCNITY_DATA_DIR`, default `<repo>/Data/raw`. Never committed.
- Commit after every task with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and the session line.

---

## File map

| Path | Responsibility |
|---|---|
| `app/pyproject.toml` | uv project, deps, `[tool.pytest]` |
| `app/start.py` | stdlib-only launcher |
| `app/.env.example` `app/.gitignore` | config template; ignore `.env .venv .web cache/` |
| `app/vcnity/config.py` | `Settings` dataclass from env |
| `app/vcnity/db.py` | `start_pg()`, `get_engine()`, `session()`, `init_db()` |
| `app/vcnity/models.py` | SQLAlchemy ORM for all 13 tables |
| `app/vcnity/providers/base.py` | `Provider` ABC, `CallResult` |
| `app/vcnity/providers/ollama_local.py` | `OllamaProvider` |
| `app/vcnity/providers/hosted_stub.py` | `HostedStub` (always refuses) |
| `app/vcnity/providers/router.py` | `get_provider`, `Level3NoAI`, `UnredactedLevel2` |
| `app/vcnity/audit.py` | `record_call(session, ...)` |
| `app/vcnity/redact.py` | `redact(text, names) -> str` |
| `app/vcnity/wordlist.py` | `load_wordlist(path) -> list[str]`, `as_hotwords` |
| `app/vcnity/stages/s0_intake.py` … `s9_reportback.py`, `concerns.py` | one stage each; each exposes `run(session, job_id, **opts)` |
| `app/vcnity/pipeline.py` | `run_stage(session, job_id, n)`, gates, `raise_level` cascade |
| `app/vcnity/export.py` | `report_to_docx(markdown, path)` |
| `app/api/app.py` | Flask app factory + routes |
| `app/ui/rxconfig.py`, `app/ui/ui/ui.py`, `app/ui/ui/state.py`, `app/ui/ui/pages/*.py` | Reflex |
| `app/scripts/precompute.py` | end-to-end run on `Data/raw` |
| `app/data/wordlist.txt` | seed word list |
| `app/tests/*` | pytest |

---

### Task 1: Skeleton, config, launcher

**Files:**
- Create: `app/pyproject.toml`, `app/.gitignore`, `app/.env.example`, `app/vcnity/__init__.py`, `app/vcnity/config.py`, `app/start.py`, `app/tests/conftest.py`
- Test: `app/tests/test_config.py`

**Interfaces:**
- Produces: `vcnity.config.settings: Settings` with fields `data_dir: Path`, `cache_dir: Path`, `pg_dir: Path`, `ollama_model: str`, `hf_token: str|None`, `allow_hosted: bool`, `small_n: int`, `safety_contact: str`, `api_port: int`, `wordlist_path: Path`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/test_config.py
from pathlib import Path
def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("VCNITY_DATA_DIR", raising=False)
    from vcnity.config import load_settings
    s = load_settings()
    assert s.data_dir.name == "raw"
    assert s.small_n == 3
    assert s.allow_hosted is False
    assert s.safety_contact.startswith("UNSET")

def test_settings_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("VCNITY_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VCNITY_SMALL_N", "5")
    from vcnity.config import load_settings
    s = load_settings()
    assert s.data_dir == tmp_path and s.small_n == 5
```

- [ ] **Step 2: Run, expect ImportError.** `uv run --project app pytest app/tests/test_config.py -v`

- [ ] **Step 3: Implement**

```python
# app/vcnity/config.py
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
load_dotenv(APP_DIR / ".env")

@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cache_dir: Path
    pg_dir: Path
    ollama_model: str
    hf_token: str | None
    allow_hosted: bool
    small_n: int
    safety_contact: str
    api_port: int
    wordlist_path: Path

def load_settings() -> Settings:
    home = Path(os.environ.get("VCNITY_HOME", Path.home() / ".vcnity"))
    return Settings(
        data_dir=Path(os.environ.get("VCNITY_DATA_DIR", REPO_DIR / "Data" / "raw")),
        cache_dir=home / "cache",
        pg_dir=home / "pgdata",
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen3.5:4b"),
        hf_token=os.environ.get("HF_TOKEN") or None,
        allow_hosted=os.environ.get("VCNITY_ALLOW_HOSTED", "0") == "1",
        small_n=int(os.environ.get("VCNITY_SMALL_N", "3")),
        safety_contact=os.environ.get("VCNITY_SAFETY_CONTACT", "UNSET — see PRD A13"),
        api_port=int(os.environ.get("VCNITY_API_PORT", "8100")),
        wordlist_path=Path(os.environ.get("VCNITY_WORDLIST", APP_DIR / "data" / "wordlist.txt")),
    )

settings = load_settings()
```

`pyproject.toml`: name `vcnity-prototype`, `requires-python = ">=3.12,<3.13"`, dependencies = the installed list, `[tool.pytest.ini_options] testpaths=["tests"] pythonpath=["."]`, `[tool.uv] package = false`.

`start.py`: set `UV_PROJECT_ENVIRONMENT` and `REFLEX_WEB_WORKDIR` under `~/.vcnity`, run `uv sync --project app`, then `subprocess.Popen` three children: `uv run python -m api.app`, `uv run reflex run` (cwd `app/ui`), and wait; Ctrl-C terminates all. Print the two URLs.

- [ ] **Step 4: Run tests, expect PASS.**
- [ ] **Step 5: Commit** `feat(app): project skeleton, settings, cross-platform launcher`

---

### Task 2: Embedded Postgres and ORM

**Files:**
- Create: `app/vcnity/db.py`, `app/vcnity/models.py`
- Test: `app/tests/test_db.py`

**Interfaces:**
- Produces: `db.start_pg() -> str` (URI), `db.get_engine(uri=None)`, `db.session()` contextmanager yielding `sqlalchemy.orm.Session`, `db.init_db()`.
- Produces ORM classes: `Job, ConsentRecord, SourceFile, Segment, Artefact, Unit, Theme, ThemeQuote, Review, IdentifyFlag, Report, Concern, AICall` with columns exactly as the spec's data model; `Unit.embedding = Column(Vector(768))`.
- `conftest.py` fixture `db_session` that starts pg in a tmp dir once per session, `init_db()`, yields a session, rolls back per test.

- [ ] **Step 1: Failing test**

```python
# app/tests/test_db.py
from vcnity.models import Job, SourceFile, Unit
def test_roundtrip_and_vector(db_session):
    job = Job(name="t", brief="b"); db_session.add(job); db_session.flush()
    f = SourceFile(job_id=job.id, filename="a.m4a", kind="audio", level=2, path="x", sha256="0"*64)
    db_session.add(f); db_session.flush()
    u = Unit(job_id=job.id, source_type="segment", source_id=1, text="hi", redacted_text="hi",
             speaker_key="S1", embedding=[0.0]*768)
    db_session.add(u); db_session.flush()
    assert db_session.get(Unit, u.id).embedding.shape == (768,)
```

- [ ] **Step 2: Run, expect failure (no module).**
- [ ] **Step 3: Implement** `db.py`: `pgserver.get_server(settings.pg_dir)` cached in a module global; `get_uri()`; engine `create_engine(uri.replace("postgresql://","postgresql+psycopg://"))`; `init_db()` runs `CREATE EXTENSION IF NOT EXISTS vector` then `Base.metadata.create_all`. `models.py`: declarative classes; enums as `String` with `CheckConstraint`s; `Theme.status` default `"draft"`; `SourceFile.level_confirmed_by_community` default False; `Unit.excluded` default False; timestamps `server_default=func.now()`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(db): embedded postgres bootstrap and ORM`

---

### Task 3: Providers, router, audit

**Files:**
- Create: `app/vcnity/providers/__init__.py`, `base.py`, `ollama_local.py`, `hosted_stub.py`, `router.py`, `app/vcnity/audit.py`
- Test: `app/tests/test_router.py`

**Interfaces:**
- `class Provider(ABC): name: str; is_local: bool; def complete(self, prompt: str, system: str = "", images: list[Path] | None = None, json_mode: bool = False) -> str`
- `class Level3NoAI(Exception)`, `class UnredactedLevel2(Exception)`, `class HostedRefused(Exception)`
- `router.get_provider(level: int, *, redacted: bool = False) -> Provider`
- `router.call(session, *, job_id, stage, level, purpose, prompt, system="", images=None, json_mode=False, redacted=False) -> str` — the one function every stage uses; it chooses the provider, calls, and writes the audit row.
- `audit.record_call(session, job_id, stage, provider, is_local, level, model, purpose)`

- [ ] **Step 1: Failing tests**

```python
# app/tests/test_router.py
import pytest
from vcnity.providers import router
from vcnity.models import AICall

class Fake(router.Provider):
    name="fake"; is_local=True
    def complete(self, prompt, system="", images=None, json_mode=False): return "ok"

def test_level3_never_reaches_a_provider(db_session, monkeypatch):
    monkeypatch.setattr(router, "_local", lambda: Fake())
    with pytest.raises(router.Level3NoAI):
        router.call(db_session, job_id=1, stage=4, level=3, purpose="t", prompt="x")
    assert db_session.query(AICall).count() == 0

def test_level2_requires_redacted(db_session, monkeypatch):
    monkeypatch.setattr(router, "_local", lambda: Fake())
    with pytest.raises(router.UnredactedLevel2):
        router.call(db_session, job_id=1, stage=4, level=2, purpose="t", prompt="x", redacted=False)
    assert router.call(db_session, job_id=1, stage=4, level=2, purpose="t", prompt="x", redacted=True) == "ok"
    row = db_session.query(AICall).one(); assert row.is_local and row.level == 2

def test_hosted_refused_even_when_allowed(monkeypatch):
    from vcnity.providers.hosted_stub import HostedStub
    with pytest.raises(router.HostedRefused):
        HostedStub().complete("x")
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** `router.get_provider`: `if level >= 3: raise Level3NoAI`; `if level == 2 and not redacted: raise UnredactedLevel2`; `if level == 1 and settings.allow_hosted: return HostedStub()` else `_local()`. `_local()` returns `OllamaProvider(settings.ollama_model)`. `OllamaProvider.complete` uses `ollama.chat(model, messages=[{"role":"system",...},{"role":"user","content":prompt,"images":[str(p) ...]}], options={"temperature":0}, format="json" if json_mode else None, think=False)` and returns `message.content`. `HostedStub.complete` always raises `HostedRefused("no hosted provider is configured (PRD A7)")`. `call()` wraps: choose → complete → `record_call` → return.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(providers): router enforcing Level 3 no-AI and Level 2 redaction, with audit log`

---

### Task 4: Redaction and word list

**Files:**
- Create: `app/vcnity/redact.py`, `app/vcnity/wordlist.py`, `app/data/wordlist.txt`
- Test: `app/tests/test_redact.py`

**Interfaces:**
- `redact(text: str, names: list[str] = ()) -> str` — replaces emails with `[email]`, AU phone numbers with `[phone]`, street addresses (`\d+ \w+ (Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Court|Ct)`) with `[address]`, each listed name (case-insensitive, whole word) with `[name]`.
- `load_wordlist(path: Path) -> list[str]` — non-empty, non-`#` lines, deduped, order kept. `as_hotwords(words) -> str` joins with `", "`. `person_names(path) -> list[str]` returns lines tagged `@person`.

- [ ] **Step 1: Failing tests**

```python
from vcnity.redact import redact
from vcnity.wordlist import load_wordlist, person_names
def test_redact_pii():
    t = "Ring Priya on 0412 345 678 or priya@example.com at 12 Nicholas Street"
    out = redact(t, names=["Priya"])
    assert "0412" not in out and "example.com" not in out and "Nicholas Street" not in out and "Priya" not in out
    assert out.count("[name]") == 1
def test_wordlist(tmp_path):
    p = tmp_path/"w.txt"; p.write_text("# c\nKelvin Grove\nPriya @person\n\nKelvin Grove\n")
    assert load_wordlist(p) == ["Kelvin Grove", "Priya"]
    assert person_names(p) == ["Priya"]
```

- [ ] **Step 2: Run, expect failures.**  - [ ] **Step 3: Implement** (regexes as above; `@person` tag stripped from the word itself).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat: level 2 redaction and community word list`

Seed `data/wordlist.txt`: `Kelvin Grove`, `QUT`, `Queensland University of Technology`, `Ipswich`, `Tulmur`, `Meanjin`, `Brisbane`, `FQI`, `Nicholas Street Precinct`, `Shape Your Ipswich`, `co-design`, `VCNITY`.

---

### Task 5: Stage 0 intake and Stage 1 ingest

**Files:**
- Create: `app/vcnity/stages/__init__.py`, `s0_intake.py`, `s1_ingest.py`
- Test: `app/tests/test_ingest.py` (fixtures built in-test with python-docx / python-pptx / PyAV)

**Interfaces:**
- `s0_intake.create_job(session, name, brief="") -> Job`; `s0_intake.add_file(session, job_id, path: Path, level: int, consent_label: str, consent_scope: str) -> SourceFile` (kind by suffix: `.m4a .wav .mp3 .mp4`→audio; `.jpg .jpeg .png .heic`→image; `.docx .pptx .txt .md`→text; `.xlsx`→brief); `set_level(session, file_id, level, actor_role)` — refuses lowering (`ValueError`); `confirm_level(session, file_id)` sets flag.
- `s1_ingest.run(session, job_id) -> list[dict]` — per file: audio → `cache_dir/<sha>.wav` 16 kHz mono (PyAV resample); image → EXIF-stripped copy `cache_dir/<sha>.jpg`; text → `cache_dir/<sha>.txt` (docx paragraphs + tables; pptx shapes' text frames, notes, and each picture saved as `cache_dir/<sha>_slideN_M.png` registered as a new image `SourceFile` inheriting level/consent); brief → concatenated `Background` cells into `Job.brief`. Writes `SourceFile.provenance = {"ingested_path", "duration_s"|"width","height"|"chars", "tool", "when"}`.
- `s1_ingest.extract_text(path: Path) -> tuple[str, list[Path]]` (pure function, used by tests).

- [ ] **Step 1: Failing tests** — build a docx with two paragraphs, a pptx with one text box and one embedded PNG, a txt; assert `extract_text` returns the words and the PNG path; assert `set_level` from 2→1 raises and 2→3 succeeds; assert a 1-second synthetic stereo 48 kHz wav becomes mono 16 kHz.
- [ ] **Step 2: Run, expect failures.**  - [ ] **Step 3: Implement.**  - [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** `feat(stages): intake with levels and consent; ingest for audio, images, text, brief`

---

### Task 6: Stage 2 transcription and 2b diarisation

**Files:**
- Create: `app/vcnity/stages/s2_transcribe.py`, `s2b_diarise.py`
- Test: `app/tests/test_transcribe.py` (no models: tests the merge and flag logic)

**Interfaces:**
- `s2_transcribe.transcribe_wav(wav: Path, hotwords: str | None, initial_prompt: str | None) -> list[dict]` — each `{"start","end","text","avg_logprob","no_speech_prob"}`; model `large-v3`, `compute_type="int8"`, `vad_filter=True`, `condition_on_previous_text=False`, `beam_size=5`, `temperature=[0.0,0.2,0.4,0.6,0.8,1.0]`, `word_timestamps=True`.
- `s2_transcribe.flag_unsure(seg: dict, threshold=-0.8) -> bool`.
- `s2_transcribe.run(session, job_id, variants=("with_wordlist","without")) -> dict` — for each audio file whose level allows AI (level==1, or level==2 and confirmed) and is not level 3: run each variant, insert `Segment` rows with `confidence = exp(avg_logprob)`, `speaker=None`. Level 3 audio: skip and record `{"file": id, "skipped": "level 3 — hand transcription"}`.
- `s2b_diarise.diarise(wav: Path) -> list[tuple[float,float,str]]` using `pyannote.audio.Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=settings.hf_token)`; returns `[]` with a logged warning if no token.
- `s2b_diarise.merge_speakers(segments: list[Segment], turns) -> None` — assigns `speaker` = label of the turn with greatest overlap; leaves None if no overlap.
- `s2_transcribe.compare(session, file_id) -> dict` — jiwer `wer` between the two variants' concatenated text plus a word-level diff list.

- [ ] **Step 1: Failing tests** — `merge_speakers` on two fake segments and three turns; `flag_unsure(-0.9)` True, `-0.3` False; `compare` on inserted segments returns `wer` between 0 and 1 and a non-empty diff.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(stages): transcription with word list variants, unsure flags, diarisation merge`

---

### Task 7: Stage 3 things people made

**Files:**
- Create: `app/vcnity/stages/s3_artefacts.py`
- Test: `app/tests/test_artefacts.py` (mock `router.call`)

**Interfaces:**
- `PROMPT_VERBATIM` — "Transcribe every piece of handwritten or printed text you can actually read in this photo, exactly as written. Keep misspellings. Do not correct, complete, or guess. For any word you cannot read, write [illegible]. Then, on a new line starting with DESCRIPTION:, describe only what is physically in the frame — materials, colours, layout, drawings — in two sentences. Do not say what anything means or symbolises."
- `parse_vlm(text) -> dict(verbatim_text, description, illegible_count)`.
- `run(session, job_id)` — for each image `SourceFile` allowed by level: `router.call(... level=file.level, purpose="artefact", images=[path], redacted=True)` (an image cannot be redacted; Level 2 images are allowed because only the *maker's own text* is read and a person checks — record this in the audit purpose `artefact-l2-human-check`), insert `Artefact`.

- [ ] **Step 1: Failing test** — `parse_vlm("PATIENCE\nKINDNESS [illegible]\nDESCRIPTION: red marker on white paper. A drawing.")` → `illegible_count==1`, description starts with "red marker".
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(stages): verbatim artefact reading with illegible markers, no interpretation`

---

### Task 8: Stage 4 draft themes and Stage 5 evidence check

**Files:**
- Create: `app/vcnity/stages/s4_themes.py`, `s5_evidence.py`
- Test: `app/tests/test_themes.py`

**Interfaces:**
- `s4_themes.build_units(session, job_id) -> int` — one `Unit` per canonical (`with_wordlist`) segment with ≥ 6 words, per artefact verbatim line group, per text file paragraph; `speaker_key` = `f"{file_id}:{speaker or 'unk'}"` for audio, `f"file:{file_id}"` otherwise; `redacted_text = redact(text, person_names(...))` when `level==2` else text; level 3 files contribute nothing.
- `s4_themes.embed(texts: list[str]) -> np.ndarray` via `SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")`.
- `s4_themes.cluster(embeddings, min_size) -> list[int]` — BERTopic with `min_topic_size=min_size`, `calculate_probabilities=False`; if it yields < 2 topics or raises, fall back to `sklearn.cluster.AgglomerativeClustering(distance_threshold=1.0, n_clusters=None, metric="cosine", linkage="average")`.
- `s4_themes.label_cluster(session, job_id, level, quotes: list[str]) -> dict(label, summary)` — `router.call(json_mode=True)` with system "You label a group of quotes. Return JSON {label, summary}. The summary may only restate what the quotes say. Never add facts."; level = max level among the quotes' files.
- `s4_themes.run(session, job_id)` — builds units, embeds, clusters, creates `Theme(status="draft")` + `ThemeQuote` rows, sets `n_people` = distinct `speaker_key`.
- `s5_evidence.check_structural(session, theme_id) -> bool` — all quotes exist and `not excluded`, count ≥ 1.
- `s5_evidence.check_grounding(session, theme) -> tuple[bool, str]` — `router.call(json_mode=True)` "Given these quotes and this summary, does the summary claim anything the quotes do not say? Return {unsupported: bool, sentence: str}".
- `s5_evidence.run(session, job_id) -> dict(unsupported=[ids])` — sets `status="unsupported"` where either check fails.

- [ ] **Step 1: Failing tests** — `cluster` on 12 synthetic 768-d vectors in three tight groups returns three labels; `check_structural` False after marking the only quote's unit `excluded`; `run` with mocked `router.call` returning `{"unsupported": true, "sentence": "x"}` marks the theme unsupported.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(stages): draft themes from cluster-member quotes; evidence check`

---

### Task 9: Stage 6 sign-off and Stage 7 identifiability

**Files:**
- Create: `app/vcnity/stages/s6_signoff.py`, `s7_identify.py`
- Test: `app/tests/test_authority.py`

**Interfaces:**
- `class AuthorityError(Exception)`
- `s6_signoff.review(session, theme_id, actor_role: str, action: str, label=None, summary=None, note="") -> Theme` — actions `confirm|fix|reject`; `actor_role=="community"` sets `status` (`confirmed|fixed|rejected`) and `decided_by="community"`; `actor_role=="analyst"` on a theme with `decided_by=="community"` raises `AuthorityError`; analyst on an undecided theme may only `note` (no status change). Writes a `Review` row with before/after JSON.
- `s6_signoff.add_theme(session, job_id, label, summary, quote_unit_ids: list[int]) -> Theme` — `status="added"`, `decided_by="community"`; at least one quote required.
- `s7_identify.run(session, job_id) -> list[IdentifyFlag]` — for themes with status in `confirmed|fixed|added`: `small_n` if `n_people < settings.small_n`; `pii` if `redact(quote) != quote` for any quote, or model scan (`router.call`, level of theme) returns `{identifying: true, why}`.
- `s7_identify.decide(session, flag_id, decision: str, reason: str)` — `decision in {keep, cut}`; empty reason → `ValueError`; `cut` sets theme `status="cut"` keeping `decided_by`.

- [ ] **Step 1: Failing tests** — community confirms → analyst `fix` raises `AuthorityError`; analyst `cut` without reason raises; `small_n` flag appears for a 2-person theme with `settings.small_n=3`.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(stages): community sign-off with locked authority; identifiability flags and analyst cuts`

---

### Task 10: Stage 8 report, Stage 9 report back, export

**Files:**
- Create: `app/vcnity/stages/s8_report.py`, `s9_reportback.py`, `app/vcnity/export.py`
- Test: `app/tests/test_report.py`

**Interfaces:**
- `s8_report.included_themes(session, job_id) -> list[Theme]` — status ∈ {confirmed, fixed, added}.
- `s8_report.theme_table(session, job_id) -> list[dict(label, n, m, pct, summary)]` — `m` = distinct `speaker_key` across all non-excluded units in the job.
- `s8_report.render_markdown(job, table, findings: str) -> str` — sections: `# {job.name}`, `## Background` (brief), `## How we engaged` (file list with kinds and dates), `## What the community told us` (table), `## Findings` (narrative), `## Sources` (per theme: quote ids only).
- `s8_report.run(session, job_id) -> Report` — findings via `router.call` on the *table only* at level = max included level, then `Report(kind="client", markdown=..., approved_community=False, approved_analyst=False)`.
- `s8_report.approve(session, report_id, actor_role)`; `s8_report.export(session, report_id, path: Path)` → raises `PermissionError` unless both approved; writes `.md` and `.docx`.
- `s9_reportback.run(session, job_id) -> Report(kind="reportback")` — model rewrites the client report in second person, short sentences, no jargon; same approve/export.
- `export.report_to_docx(markdown: str, path: Path)` — headings, paragraphs, and the theme table as a real Word table.

- [ ] **Step 1: Failing tests** — a rejected and a cut theme are absent from `theme_table`; `pct == round(100*n/m)`; `export` raises before both approvals and writes both files after.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(stages): council-style report with dual approval and docx export; plain-language report back`

---

### Task 11: Pipeline orchestrator, level gates, raise-to-3 cascade

**Files:**
- Create: `app/vcnity/pipeline.py`
- Test: `app/tests/test_pipeline.py`

**Interfaces:**
- `STAGES: dict[int, Callable]` mapping 0–9 (0 is a no-op that validates every file has consent and a level).
- `class GateError(Exception)`
- `run_stage(session, job_id, n: int, **opts) -> dict` — before stages 2,3,4,5,8,9: raise `GateError` if any non-level-3 file has `level > 1 and not level_confirmed_by_community`; before 8: raise if any open `IdentifyFlag` has no decision; records `Job.status = f"stage{n}:done"`.
- `raise_level(session, file_id, new_level)` — calls `set_level`; if `new_level == 3`: mark that file's `Unit`s `excluded=True`, delete their `ThemeQuote`s, rerun `s5_evidence.check_structural` for touched themes and set `unsupported` where it fails.

- [ ] **Step 1: Failing tests** — `run_stage(…, 2)` raises `GateError` on an unconfirmed L2 file; after `raise_level(…,3)` the theme whose only quote came from that file is `unsupported` and its unit is `excluded`.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(pipeline): stage runner with level-confirmation gates and raise-to-3 cascade`

---

### Task 12: Concerns

**Files:**
- Create: `app/vcnity/stages/concerns.py`
- Test: `app/tests/test_concerns.py`

**Interfaces:**
- `ROUTING = {"harm": ("safety_contact", 3), "misuse": ("analyst", 2), "conduct": ("community_org+vcnity", 2), "ai_error": ("analyst", None)}`
- `raise_concern(session, job_id, stage: int, text: str) -> Concern` (category None, status "new").
- `sort_concern(session, concern_id, category: str, material_level: int | None = None) -> Concern` — sets `routed_to` (safety_contact resolves to `settings.safety_contact`), `level` (None → `material_level`), `status="routed"`.

- [ ] **Step 1: Failing test** — harm routes to the configured contact at level 3; ai_error with `material_level=2` gets level 2.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat: raise-a-concern with person-sorted routing`

---

### Task 13: Flask API

**Files:**
- Create: `app/api/__init__.py`, `app/api/app.py`
- Test: `app/tests/test_api.py` (Flask test client; `router.call` mocked)

**Routes** (JSON):
`POST /jobs` {name} · `GET /jobs/<id>` · `POST /jobs/<id>/files` multipart {file, level, consent_label, consent_scope} · `PATCH /files/<id>/level` {level, actor_role} → 400 on lowering · `POST /files/<id>/confirm` · `POST /jobs/<id>/run/<n>` → 202 and a thread; `GET /jobs/<id>/status` · `GET /jobs/<id>/segments?variant=` · `GET /jobs/<id>/compare/<file_id>` · `GET /jobs/<id>/artefacts` · `PATCH /artefacts/<id>` {maker_statement} · `GET /jobs/<id>/themes` (never returns `unsupported`) · `PATCH /themes/<id>` {actor_role, action, label, summary, note} → 409 on `AuthorityError` · `POST /jobs/<id>/themes` (add) · `GET /jobs/<id>/flags` · `POST /flags/<id>/decide` {decision, reason} → 400 on empty reason · `GET /jobs/<id>/reports` · `POST /reports/<id>/approve` {actor_role} · `GET /reports/<id>/export` → 403 until both approvals, else the .docx · `POST /jobs/<id>/concerns` · `GET /jobs/<id>/concerns` · `POST /concerns/<id>/sort` · `GET /jobs/<id>/audit` → `{level3_calls, hosted_calls_l2plus, total}` · `GET /wordlist` / `PUT /wordlist` · `GET /health`.

- [ ] **Step 1: Failing tests** — lowering 2→1 gives 400; analyst PATCH after community confirm gives 409; export before approval 403; `/audit` shows zeros.
- [ ] **Step 2–4.**  - [ ] **Step 5: Commit** `feat(api): flask endpoints over the pipeline`

---

### Task 14: Reflex UI

**Files:**
- Create: `app/ui/rxconfig.py`, `app/ui/ui/__init__.py`, `app/ui/ui/ui.py`, `app/ui/ui/state.py`, `app/ui/ui/api_client.py`, `app/ui/ui/pages/{intake,pipeline,transcript,artefacts,themes,signoff,identify,report,reportback,concerns}.py`

**Behaviour:**
- `api_client.py`: thin `httpx` wrappers for every route in Task 13, base URL from `VCNITY_API_URL` (default `http://127.0.0.1:8100`).
- `state.py`: one `AppState(rx.State)` with `job_id`, `role` (dropdown: facilitator / community / analyst / client), per-page lists, and event handlers that call `api_client` and reload.
- Layout: left nav listing the ten stages with a status dot from `/status`; top bar with role selector, "Raise a concern" button (opens a dialog with `text` + current stage), and the audit panel "Level 3 → AI: 0 · hosted calls on L2+: 0".
- Each stage page has a **Re-run** button → `POST /run/<n>` and polls `/status` every 2 s while running.
- Intake: table of files with level select (options ≥ current), consent label, confirm checkbox (community role only), word list editor.
- Transcript: file tabs; two columns (with / without word list) with diffed words highlighted; unsure segments tinted; speaker column; "paste reference transcript" box → WER.
- Artefacts: photo, verbatim text with `[illegible]` counted, description, maker statement input.
- Themes: cards with label, summary, `n_people`, quotes (collapsible).
- Sign-off: community role sees confirm / fix / reject per card and an "Add a theme" form; analyst role sees a locked badge on community-decided themes and a note box only.
- Identify: flag list with keep/cut + reason (analyst only).
- Report / Report back: rendered Markdown, two approval switches (each enabled only for its role), Export button (disabled until both).
- Concerns: list; analyst sorts category; shows routed_to and level.

- [ ] **Step 1: `reflex init` in `app/ui` with `REFLEX_WEB_WORKDIR` set; confirm `reflex run` serves the default page.**
- [ ] **Step 2: Build pages against the API (API running on the precomputed DB).**
- [ ] **Step 3: Walk every page in a browser; screenshot each for the demo notes.**
- [ ] **Step 4: Commit** `feat(ui): reflex pages for all ten stages, roles, concerns, audit panel`

---

### Task 15: Precompute, README, run on Data/raw

**Files:**
- Create: `app/scripts/precompute.py`, `app/README.md`

- [ ] **Step 1: `precompute.py`** — creates the job "FQI co-design session — Sept 2026", adds the five files (recordings L2, photos L2, consent labels "session-consent-2026-09-03"), loads the xlsx as brief, confirms levels (flag `--confirm-levels` so the demo can also show the gate), runs stages 1→9 in order, prints per-stage timings, writes `~/.vcnity/cache/precompute.log`.
- [ ] **Step 2: Run it** in the background (`uv run --project app python app/scripts/precompute.py --confirm-levels`); expect ≈2 h. Diarisation runs only if `HF_TOKEN` is present; otherwise the script prints the instruction and continues.
- [ ] **Step 3: Read the outputs** — transcript sample, artefact verbatim text against the photos, theme list, report Markdown. Fix prompts if the model interprets art or fabricates.
- [ ] **Step 4: README** — prerequisites (uv, Ollama with `qwen3.5:4b`, optional HF token), `python app/start.py`, demo script (the order to click through, what to say at each stage, the two live demonstrations: raise a photo to Level 3 and watch its quotes leave the themes; analyst tries to override a community decision and gets refused).
- [ ] **Step 5: Commit** `feat: precompute script and demo README`

---

## Self-review

- Spec coverage: rules → Tasks 3, 9, 11; ten stages → Tasks 5–10; text inputs → Task 5; word-list comparison → Task 6; council-style report → Task 10; concerns → Task 12; audit panel → Tasks 3, 13, 14; launcher/cross-platform → Task 1; precompute + re-run → Tasks 13–15. No gaps found.
- Names used across tasks: `router.call`, `redact`, `person_names`, `set_level`, `confirm_level`, `AuthorityError`, `GateError`, `included_themes`, `theme_table` — consistent.
