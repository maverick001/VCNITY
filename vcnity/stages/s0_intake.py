"""Stage 1 — Data Ingest, the people half (PRD §4 stage 0, Intake). Ties every file to a consent record and a sensitivity level.
Nothing gets in without both.

Levels only go up. The facilitator sets one on upload; the community can raise
it any time; nothing lowers it. Nothing above Level 1 goes near AI until a
community reviewer confirms the level (PRD A9).

Also here: how many people came to each session (the report's "of M", PRD A6),
and the set of themes agreed with the community before anything is sorted
(PRD A17).

The conversion half (formats, provenance, pulling the words out) is s1_ingest,
which the pipeline runs straight after this.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..models import ConsentRecord, Job, Review, SourceFile, Theme

KIND_BY_SUFFIX = {
    ".m4a": "audio", ".wav": "audio", ".mp3": "audio", ".mp4": "audio", ".aac": "audio", ".flac": "audio",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".heic": "image", ".webp": "image",
    ".docx": "text", ".pptx": "text", ".txt": "text", ".md": "text",
    ".xlsx": "brief",
}


def kind_for(path: Path) -> str:
    try:
        return KIND_BY_SUFFIX[Path(path).suffix.lower()]
    except KeyError as e:
        raise ValueError(f"unsupported file type: {path}") from e


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def create_job(session, name: str, brief: str = "") -> Job:
    job = Job(name=name, brief=brief, status="intake")
    session.add(job)
    session.flush()
    return job


def add_file(
    session, job_id: int, path: Path, *, level: int, consent_label: str, consent_scope: str = ""
) -> SourceFile:
    if level not in (1, 2, 3):
        raise ValueError("level must be 1, 2 or 3")
    if not consent_label:
        raise ValueError("a consent record is required (PRD §4 stage 0)")
    path = Path(path)
    consent = ConsentRecord(job_id=job_id, participant_label=consent_label, granted=True, scope_text=consent_scope)
    session.add(consent)
    session.flush()
    sf = SourceFile(
        job_id=job_id, filename=path.name, kind=kind_for(path), level=level,
        consent_id=consent.id, sha256=sha256_of(path), path=str(path), provenance={},
    )
    session.add(sf)
    session.flush()  # assigns sf.id
    sf.filename = f"{sf.id}_{path.name}"  # so the id shown elsewhere (e.g. the transcript picker) is findable by name
    session.flush()
    return sf


def set_level(session, file_id: int, level: int, *, actor_role: str) -> SourceFile:
    sf = session.get(SourceFile, file_id)
    if sf is None:
        raise KeyError(file_id)
    if level not in (1, 2, 3):
        raise ValueError("level must be 1, 2 or 3")
    if level < sf.level:
        raise ValueError(f"levels only go up (is {sf.level}, asked for {level}); nothing lowers it")
    if level != sf.level:
        sf.level = level
        # A raised level needs confirming again before AI may run.
        sf.level_confirmed_by_community = False
    session.flush()
    return sf


def confirm_level(session, file_id: int) -> SourceFile:
    sf = session.get(SourceFile, file_id)
    if sf is None:
        raise KeyError(file_id)
    sf.level_confirmed_by_community = True
    session.flush()
    return sf


def set_attendance(session, job_id: int, sessions: list[dict]) -> Job:
    """Replace the job's attendance: one row per session, entered by the facilitator."""
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    rows = []
    for r in sessions:
        name = str(r.get("session", "")).strip()
        try:
            count = int(r.get("count"))
        except (TypeError, ValueError):
            raise ValueError(f"attendance for '{name or '?'}' must be a whole number") from None
        if not name:
            raise ValueError("each attendance row needs a session name")
        if count < 0:
            raise ValueError("attendance can't be negative")
        rows.append({"session": name, "count": count})
    job.attendance = rows
    session.flush()
    return job


def attendance_total(job: Job) -> int:
    return sum(int(r.get("count", 0)) for r in (job.attendance or []))


def add_agreed_theme(session, job_id: int, label: str, summary: str, *, level: int = 1,
                     actor_role: str = "community") -> Theme:
    """A theme agreed with the community before sorting. The community's words, so it starts signed off."""
    if actor_role != "community":
        raise PermissionError("the theme set is agreed with the community (PRD §4 stage 0)")
    if level not in (1, 2):
        raise ValueError("a theme's wording is Level 1 or 2; Level 3 wording can't go in a report")
    if not label.strip():
        raise ValueError("an agreed theme needs a label")
    t = Theme(job_id=job_id, label=label.strip()[:200], summary=summary.strip(), status="confirmed",
              decided_by="community", agreed_upfront=True, level=level)
    session.add(t)
    session.flush()
    session.add(Review(theme_id=t.id, actor_role="community", action="agree",
                       after={"label": t.label, "summary": t.summary, "status": t.status}))
    session.flush()
    return t


def run(session, job_id: int) -> dict:
    """Stage 0 as a pipeline step: verify every file has consent and a level."""
    files = session.query(SourceFile).filter_by(job_id=job_id).all()
    missing = [f.filename for f in files if f.consent_id is None or f.level not in (1, 2, 3)]
    if missing:
        raise ValueError(f"files without consent or level: {missing}")
    return {"files": len(files), "levels": {f.filename: f.level for f in files}}
