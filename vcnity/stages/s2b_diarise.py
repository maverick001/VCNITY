"""Stage 2b — who's speaking. A pyannote speaker-diarization pipeline, fully local
after the one-time download: 3.1 by default, or community-1 if the analyst picks
it for the job (model_choice.py). Needs HF_TOKEN; without it the stage says so and
leaves speakers blank rather than failing the pipeline.
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path

from .. import model_choice
from ..audit import record_call
from ..config import settings
from ..models import Job, Segment, SourceFile
from ._gate import ai_allowed, why_not

log = logging.getLogger(__name__)
DIAR_MODEL = model_choice.DEFAULT_DIARISE
_pipeline = None
_pipeline_name = ""


def _pipe(name: str = DIAR_MODEL):
    """One speaker model in memory at a time: a different one replaces it rather than joining it."""
    global _pipeline, _pipeline_name
    if _pipeline is None or _pipeline_name != name:
        from pyannote.audio import Pipeline

        _pipeline = None  # let the old one go before the new one loads — 16GB, no GPU
        _pipeline = Pipeline.from_pretrained(name, token=settings.hf_token)
        _pipeline_name = name
    return _pipeline


def _load_wav(wav: Path) -> dict:
    """Stage 1's 16 kHz mono 16-bit WAV, as the in-memory form pyannote accepts.
    Handing pyannote a path makes it decode with torchcodec, which needs FFmpeg's
    shared DLLs on Windows; the app avoids a system FFmpeg (stage 1 uses PyAV)."""
    import numpy as np
    import torch

    with wave.open(str(wav), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    x = x.reshape(-1, ch).T  # (channel, time)
    return {"waveform": torch.from_numpy(np.ascontiguousarray(x)), "sample_rate": sr}


def diarise(wav: Path, model_name: str = DIAR_MODEL) -> list[tuple[float, float, str]]:
    if not settings.hf_token:
        log.warning("HF_TOKEN not set — skipping diarisation (see app/.env.example)")
        return []
    result = _pipe(model_name)(_load_wav(wav))
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
    name = model_choice.chosen_diarise(session, job_id)
    report: dict = {"files": [], "token_present": bool(settings.hf_token), "model": name}
    q = session.query(SourceFile).filter_by(job_id=job_id, kind="audio")
    if files:
        q = q.filter(SourceFile.id.in_(files))
    for sf in q.all():
        entry = {"file_id": sf.id, "filename": sf.filename}
        if not ai_allowed(sf):
            entry["skipped"] = why_not(sf)
        else:
            wav = Path(sf.provenance.get("ingested_path", ""))
            turns = diarise(wav, name) if wav.exists() else []
            segs = session.query(Segment).filter_by(file_id=sf.id).all()
            merge_speakers(segs, turns)
            entry["turns"] = len(turns)
            entry["speakers"] = sorted({t[2] for t in turns})
            if turns:
                record_call(session, job_id=job_id, stage=2, provider=f"pyannote:{name}", is_local=True,
                            level=sf.level, model=name, purpose="diarisation")
        report["files"].append(entry)
    job = session.get(Job, job_id)
    job.status = "stage2b:done"
    session.flush()
    return report
