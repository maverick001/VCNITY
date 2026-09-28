"""Chat with Data — a chat box for the facilitator and the analyst about one job's
material (PRD A19).

It answers only from the material: the question is embedded, the closest
passages are found, and the local text model answers from those passages and a
short summary of the job, citing each passage it used as [S12]. A citation to a
passage it wasn't given is stripped before anyone sees the answer.

What it reads: every file below Level 3 — Level 1 as it is, Level 2 with real
names swapped for made-up ones (the PRD's rule for any AI step on Level 2). It
includes Level 2 files before the name check and before the community confirms
the level, because the people who can ask already see those files (PRD A19).
Level 3 never reaches it; the router refuses it anyway.

What it won't do: say what anything means. That's the community's call at
sign-off. Nothing is stored except the usual ai_calls row, which records that a
question was asked, not what it said.
"""
from __future__ import annotations

import hashlib
import pickle
import re
import threading

import numpy as np

from .config import settings
from .models import Job, Segment, SourceFile, Theme, Unit
from .providers import router
from .redact import next_fake, pseudonymise
from .stages import s0_intake, s4_themes
from .wordlist import person_names

ROLES = ("facilitator", "analyst")
TOP_K = 12
HISTORY_TURNS = 4
_vectors: dict[str, np.ndarray] = {}  # passage text → embedding, so a second question doesn't re-embed a job
_VECTOR_CACHE_MAX = 20000
# Embedding a job's material takes minutes on a laptop CPU, so each passage is embedded once and kept on disk,
# keyed by a hash of its text (the text itself isn't stored). It lives in ~/.vcnity, never in the repo.
_disk: dict[str, np.ndarray] | None = None
_disk_lock = threading.Lock()


def _disk_path():
    return settings.cache_dir / "ask_vectors.pkl"


def _key(text: str) -> str:
    return hashlib.sha1(f"{s4_themes.EMBED_MODEL}|{text}".encode("utf-8")).hexdigest()


def _load_disk() -> dict[str, np.ndarray]:
    global _disk
    if _disk is None:
        try:
            with open(_disk_path(), "rb") as f:
                _disk = pickle.load(f)
        except (OSError, pickle.PickleError, EOFError):
            _disk = {}
    return _disk


def _save_disk() -> None:
    path = _disk_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(_disk, f)
    tmp.replace(path)

SYSTEM = (
    "You answer questions from a facilitator or analyst about material from a community co-design job. "
    "Use ONLY the JOB SUMMARY and the PASSAGES given. After every sentence that uses a passage, cite it like [S3]. "
    "If the answer isn't in the material, say you can't find it there. "
    "Never say what the material means, what people really felt or intended, or what anything symbolises — "
    "that is for the community to decide at sign-off; say so if asked. "
    "Names in the passages may be made-up stand-ins; use them as written. Plain English, short answers."
)
PROMPT = "JOB SUMMARY:\n{summary}\n\nPASSAGES:\n{passages}\n\n{history}QUESTION: {question}"
_CITE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")  # [S3] or a group like [S3, S7]


class AskError(ValueError):
    """The question can't be asked (empty, wrong role)."""


def _names(session, job_id: int) -> dict[str, str]:
    """The job's name list, plus word-list names it doesn't have yet — in memory only."""
    mapping = s4_themes.name_map(session, job_id)
    known = {r.lower() for r in mapping}
    reals = set(mapping)
    for n in person_names(settings.wordlist_path):
        if n.lower() not in known:
            reals.add(n)
            mapping[n] = next_fake(set(mapping.values()), reals)
            known.add(n.lower())
    return mapping


def _clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _stored_vectors(session, job_id: int) -> None:
    """Stage 4 already embedded most of a job's material with the same model; reuse that, don't redo it."""
    for text, vec in session.query(Unit.redacted_text, Unit.embedding).filter(
            Unit.job_id == job_id, Unit.embedding.isnot(None)):
        if text not in _vectors:
            _vectors[text] = np.asarray(vec, dtype=float)


def passages(session, job_id: int) -> list[dict]:
    """Every quotable bit of every file below Level 3, as the model will see it and as a person reads it."""
    _stored_vectors(session, job_id)
    mapping = _names(session, job_id)
    out: list[dict] = []
    files = (session.query(SourceFile).filter(SourceFile.job_id == job_id, SourceFile.level < 3,
                                              SourceFile.kind != "brief").order_by(SourceFile.id).all())
    for sf in files:
        segs = {s.id: s for s in session.query(Segment).filter_by(file_id=sf.id, variant="with_wordlist")}
        for source_type, source_id, text, speaker in s4_themes._rows_for(session, sf):
            if source_type == "segment" and source_id in segs:
                where = f"{_clock(segs[source_id].start_s)}" + (f", {speaker}" if speaker else "")
            elif source_type == "text":
                where = f"paragraph {source_id + 1}"
            else:
                where = "photo"
            out.append({"id": f"S{len(out) + 1}", "file": sf.filename, "where": where, "level": sf.level,
                        "text": text, "model_text": pseudonymise(text, mapping) if sf.level == 2 else text})
    return out


def _embed(texts: list[str]) -> np.ndarray:
    with _disk_lock:
        disk = _load_disk()
        for t in dict.fromkeys(texts):
            if t not in _vectors and _key(t) in disk:
                _vectors[t] = disk[_key(t)]
    missing = [t for t in dict.fromkeys(texts) if t not in _vectors]
    if missing:
        if len(_vectors) + len(missing) > _VECTOR_CACHE_MAX:
            keep = {t: _vectors[t] for t in texts if t in _vectors}
            _vectors.clear()
            _vectors.update(keep)
        new = {t: np.asarray(v, dtype=np.float32) for t, v in zip(missing, s4_themes.embed(missing))}
        _vectors.update(new)
        with _disk_lock:
            disk = _load_disk()
            disk.update({_key(t): v for t, v in new.items()})
            _save_disk()
    return np.vstack([_vectors[t] for t in texts])


def retrieve(question: str, items: list[dict], k: int = TOP_K) -> list[dict]:
    """The k passages closest to the question, in their original order."""
    if not items:
        return []
    X = _embed([p["model_text"] for p in items])
    q = np.asarray(s4_themes.embed([question]))[0]
    best = np.argsort(-(X @ q))[:k]
    return [items[i] for i in sorted(best)]


def job_summary(session, job_id: int) -> str:
    from . import pipeline

    job = session.get(Job, job_id)
    st = pipeline.status(session, job_id)
    lines = [f"Job: {job.name}"]
    for f in session.query(SourceFile).filter_by(job_id=job_id).order_by(SourceFile.id):
        extra = f", {round(f.provenance['duration_s'] / 60)} min" if (f.provenance or {}).get("duration_s") else ""
        note = " (Level 3 — not readable here)" if f.level >= 3 else ""
        lines.append(f"- file {f.filename}: {f.kind}, Level {f.level}{extra}{note}")
    total = s0_intake.attendance_total(job)
    lines.append(f"Attendance: {total} people" if total else "Attendance: not entered yet")
    for t in session.query(Theme).filter(Theme.job_id == job_id, Theme.status != "unsupported").order_by(Theme.id):
        counted = f"{t.people_count} people counted" if t.people_count is not None else "not counted"
        lines.append(f"- theme '{t.label}': {t.status}, {len(t.quotes)} quotes, {counted}")
    lines.append("Stages: " + "; ".join(f"{s['n']} {s['name']} {'done' if s['done'] else 'not done'}"
                                        + (f" (waiting: {s['waiting']})" if s.get("waiting") else "")
                                        for s in st["stages"]))
    return "\n".join(lines)


def ask(session, job_id: int, question: str, *, actor_role: str, history: list[dict] | None = None) -> dict:
    if actor_role not in ROLES:
        raise PermissionError("only the facilitator or the analyst can ask questions about the material")
    question = (question or "").strip()
    if not question:
        raise AskError("ask a question first")
    if session.get(Job, job_id) is None:
        raise KeyError(job_id)
    found = retrieve(question, passages(session, job_id))
    level = max([1] + [p["level"] for p in found])
    turns = [h for h in (history or []) if h.get("role") in ("user", "assistant")][-2 * HISTORY_TURNS:]
    history_text = "".join(f"{'Q' if h['role'] == 'user' else 'A'}: {h.get('text', '')}\n" for h in turns)
    raw = router.call(
        session, job_id=job_id, stage=0, level=level, purpose="ask-a-question",
        prompt=PROMPT.format(summary=job_summary(session, job_id),
                             passages="\n".join(f"[{p['id']}] ({p['file']}, {p['where']}) {p['model_text']}"
                                                for p in found) or "(no readable material yet)",
                             history=f"EARLIER IN THIS CHAT:\n{history_text}\n" if history_text else "",
                             question=question),
        system=SYSTEM, redacted=True, max_tokens=700,
    )
    by_id = {p["id"]: p for p in found}
    cited: list[str] = []

    def keep_real(m: re.Match) -> str:
        ids = [i for i in re.split(r"\s*,\s*", m.group(1)) if i in by_id]
        cited.extend(i for i in ids if i not in cited)
        return f"[{', '.join(ids)}]" if ids else ""

    answer = re.sub(r"\s+([.,;])", r"\1", _CITE.sub(keep_real, raw)).strip()  # no gap left where a citation went
    return {"answer": answer,
            "sources": [{k: by_id[c][k] for k in ("id", "file", "where", "text")} for c in cited]}
