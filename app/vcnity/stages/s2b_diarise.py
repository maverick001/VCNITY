"""Stage 2b — who's speaking. pyannote speaker-diarization-3.1, fully local
after the one-time download. Needs HF_TOKEN; without it the stage says so and
leaves speakers blank rather than failing the pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..audit import record_call
from ..config import settings
from ..models import Job, Segment, SourceFile
from ._gate import ai_allowed, why_not

log = logging.getLogger(__name__)
DIAR_MODEL = "pyannote/speaker-diarization-3.1"
_pipeline = None


def _pipe():
    global _pipeline
    if _pipeline is None:
        from pyannote.audio import Pipeline

        _pipeline = Pipeline.from_pretrained(DIAR_MODEL, token=settings.hf_token)
    return _pipeline


def diarise(wav: Path) -> list[tuple[float, float, str]]:
    if not settings.hf_token:
        log.warning("HF_TOKEN not set — skipping diarisation (see app/.env.example)")
        return []
    result = _pipe()(str(wav))
    # pyannote 4 returns a DiarizeOutput; 3.x returned an Annotation directly.
    ann = getattr(result, "speaker_diarization", result)
    turns = []
    for turn, _, label in ann.itertracks(yield_label=True):
        turns.append((float(turn.start), float(turn.end), str(label)))
    return turns


def merge_speakers(segments, turns: list[tuple[float, float, str]]) -> None:
    """Give each segment the speaker whose turn overlaps it most. None if no overlap."""
    for seg in segments:
        best, best_ov = None, 0.0
        for start, end, label in turns:
            ov = min(seg.end_s, end) - max(seg.start_s, start)
            if ov > best_ov:
                best, best_ov = label, ov
        seg.speaker = best


def run(session, job_id: int, files: list[int] | None = None) -> dict:
    report: dict = {"files": [], "token_present": bool(settings.hf_token)}
    q = session.query(SourceFile).filter_by(job_id=job_id, kind="audio")
    if files:
        q = q.filter(SourceFile.id.in_(files))
    for sf in q.all():
        entry = {"file_id": sf.id, "filename": sf.filename}
        if not ai_allowed(sf):
            entry["skipped"] = why_not(sf)
        else:
            wav = Path(sf.provenance.get("ingested_path", ""))
            turns = diarise(wav) if wav.exists() else []
            segs = session.query(Segment).filter_by(file_id=sf.id).all()
            merge_speakers(segs, turns)
            entry["turns"] = len(turns)
            entry["speakers"] = sorted({t[2] for t in turns})
            if turns:
                record_call(session, job_id=job_id, stage=2, provider=f"pyannote:{DIAR_MODEL}", is_local=True,
                            level=sf.level, model=DIAR_MODEL, purpose="diarisation")
        report["files"].append(entry)
    job = session.get(Job, job_id)
    job.status = "stage2b:done"
    session.flush()
    return report
