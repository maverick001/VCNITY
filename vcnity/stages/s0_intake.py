"""Stage 0 — Intake. Ties every file to a consent record and a sensitivity level.
Nothing gets in without both.

Levels only go up. The facilitator sets one on upload; the community can raise
it any time; nothing lowers it. Nothing above Level 1 goes near AI until a
community reviewer confirms the level (PRD A4).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..models import ConsentRecord, Job, SourceFile

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


def run(session, job_id: int) -> dict:
    """Stage 0 as a pipeline step: verify every file has consent and a level."""
    files = session.query(SourceFile).filter_by(job_id=job_id).all()
    missing = [f.filename for f in files if f.consent_id is None or f.level not in (1, 2, 3)]
    if missing:
        raise ValueError(f"files without consent or level: {missing}")
    return {"files": len(files), "levels": {f.filename: f.level for f in files}}
