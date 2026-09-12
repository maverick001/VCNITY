"""Stage 2 — Transcription. Speech to text that copes with how people talk.

Runs faster-whisper large-v3 twice per recording: once with the community word
list, once without, so the §5 headline measure has something to show. The
`with_wordlist` run is the one the rest of the pipeline uses.

Segments the model is not sure about are flagged — "anything the AI isn't sure
about goes to a person".
"""
from __future__ import annotations

import math
from difflib import SequenceMatcher
from pathlib import Path

from ..audit import record_call
from ..config import settings
from ..models import Job, Segment, SourceFile
from ..wordlist import as_hotwords, load_wordlist
from ._gate import ai_allowed, why_not

import os

# large-v3 is the recommendation for accented, code-switched, far-field audio.
# large-v3-turbo is ~4x faster and ~1 GB smaller if the laptop is short of RAM.
ASR_MODEL = os.environ.get("VCNITY_ASR_MODEL", "large-v3")
UNSURE_LOGPROB = -0.8
UNSURE_NO_SPEECH = 0.6

_model = None


def _asr():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(ASR_MODEL, device="cpu", compute_type="int8",
                              download_root=str(settings.cache_dir / "models"))
    return _model


def flag_unsure(seg: dict, logprob_threshold: float = UNSURE_LOGPROB,
                no_speech_threshold: float = UNSURE_NO_SPEECH) -> bool:
    return seg["avg_logprob"] < logprob_threshold or seg["no_speech_prob"] > no_speech_threshold


def transcribe_wav(wav: Path, hotwords: str | None = None, initial_prompt: str | None = None) -> list[dict]:
    model = _asr()
    segments, _info = model.transcribe(
        str(wav),
        beam_size=5,
        best_of=5,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "threshold": 0.35},
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        hotwords=hotwords or None,
        initial_prompt=initial_prompt or None,
    )
    out = []
    for s in segments:
        out.append({
            "start": float(s.start), "end": float(s.end), "text": s.text.strip(),
            "avg_logprob": float(s.avg_logprob), "no_speech_prob": float(s.no_speech_prob),
        })
    return out


def run(session, job_id: int, variants=("with_wordlist", "without"), files: list[int] | None = None,
        force: bool = False) -> dict:
    """Transcribe each allowed recording, once per variant.

    Commits after every file/variant and skips any that already have segments,
    so a run that gets killed part-way (this is a laptop) resumes where it
    stopped instead of starting over. `force=True` re-does everything.
    """
    words = load_wordlist(settings.wordlist_path)
    hot = as_hotwords(words)
    prompt = ("A community co-design session in Queensland, Australia. "
              f"Names and places that may come up: {hot}.") if words else None
    report: dict = {"files": [], "model": ASR_MODEL}
    q = session.query(SourceFile).filter_by(job_id=job_id, kind="audio")
    if files:
        q = q.filter(SourceFile.id.in_(files))
    for sf in q.all():
        entry = {"file_id": sf.id, "filename": sf.filename}
        if not ai_allowed(sf):
            entry["skipped"] = why_not(sf)
            report["files"].append(entry)
            continue
        wav = Path(sf.provenance.get("ingested_path", ""))
        if not wav.exists():
            entry["skipped"] = "not ingested yet (run stage 1)"
            report["files"].append(entry)
            continue
        for variant in variants:
            existing = session.query(Segment).filter_by(file_id=sf.id, variant=variant).count()
            if existing and not force:
                entry[variant] = f"{existing} (already done)"
                continue
            if existing:
                session.query(Segment).filter_by(file_id=sf.id, variant=variant).delete(synchronize_session=False)
            use_words = variant == "with_wordlist"
            segs = transcribe_wav(wav, hotwords=hot if use_words else None,
                                  initial_prompt=prompt if use_words else None)
            for s in segs:
                session.add(Segment(
                    file_id=sf.id, variant=variant, start_s=s["start"], end_s=s["end"], text=s["text"],
                    confidence=round(math.exp(s["avg_logprob"]), 3), unsure=flag_unsure(s),
                ))
            record_call(session, job_id=job_id, stage=2, provider=f"faster-whisper:{ASR_MODEL}",
                        is_local=True, level=sf.level, model=ASR_MODEL,
                        purpose=f"asr-{variant}" + ("-l2-local-human-check" if sf.level == 2 else ""))
            session.commit()  # bank this variant now; a kill mid-run keeps it
            entry[variant] = len(segs)
        report["files"].append(entry)
    job = session.get(Job, job_id)
    job.status = "stage2:done"
    session.flush()
    return report


# ---------- comparison (PRD §5, first measure) ----------


def wer(reference: str, hypothesis: str) -> float:
    import jiwer

    if not reference.strip():
        return 0.0
    return float(jiwer.wer(reference, hypothesis))


def _text(session, file_id: int, variant: str) -> str:
    rows = (session.query(Segment).filter_by(file_id=file_id, variant=variant)
            .order_by(Segment.start_s).all())
    return " ".join(r.text for r in rows)


def compare(session, file_id: int, reference: str | None = None) -> dict:
    """What the word list changed — and, if a person pasted a reference, what it fixed."""
    without, with_ = _text(session, file_id, "without"), _text(session, file_id, "with_wordlist")
    a, b = without.split(), with_.split()
    diff = []
    changed = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            diff.append({"kind": "same", "text": " ".join(a[i1:i2])})
        else:
            diff.append({"kind": "changed", "without": " ".join(a[i1:i2]), "with": " ".join(b[j1:j2])})
            changed += max(i2 - i1, j2 - j1)
    out = {
        "file_id": file_id,
        "wer_between_runs": round(wer(without, with_), 4),
        "words_changed": changed,
        "words_total": max(len(a), 1),
        "diff": diff,
        "note": "wer_between_runs is how much the word list changed the transcript, not accuracy.",
    }
    if reference and reference.strip():
        out["wer_without_vs_reference"] = round(wer(reference, without), 4)
        out["wer_with_vs_reference"] = round(wer(reference, with_), 4)
        out["note"] = "WER against the pasted human-corrected reference. Lower is better."
    return out
