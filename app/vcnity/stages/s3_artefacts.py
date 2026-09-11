"""Stage 3 — Things people made. Describes what's in the photo, nothing more.

The model reads the words that are physically there and describes what is in
the frame. It is told, in the prompt, never to say what anything means. Meaning
comes from what the maker said about their own work — the `maker_statement`
field, which a person fills in.

Level 2 images: an image cannot be redacted, and the text being read is the
maker's own. It runs locally and a person checks it at sign-off, which is what
"a person must check it" asks for. That reasoning is recorded in the audit row.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models import Artefact, Job, SourceFile
from ..providers import router
from ._gate import ai_allowed, why_not

SYSTEM = (
    "You transcribe handwritten and printed text from photographs of things people made "
    "in a community workshop. You never interpret. You never guess."
)

PROMPT_VERBATIM = (
    "Transcribe every piece of handwritten or printed text you can actually read in this photo, "
    "exactly as written, one item per line. Keep misspellings and odd grammar exactly as they are. "
    "Do not correct, complete, or guess a word. For any word you cannot read, write [illegible]. "
    "If a whole region is too small or blurred to read, write [illegible] once for that region and move on. "
    "Never write the same line twice. Stop when you have covered the photo. "
    "Then, on a new line starting with DESCRIPTION:, describe only what is physically in the frame — "
    "materials, colours, layout, drawings — in two sentences. "
    "Do not say what anything means, symbolises, or suggests. Do not describe feelings."
)
MAX_TOKENS = 700
DEGENERATE_NOTE = "[model output repeated itself and was cut short — a person should read this artefact]"

_ILLEGIBLE = re.compile(r"\[illegible\]", re.IGNORECASE)
_HAS_WORD = re.compile(r"[A-Za-z0-9]")


def _clean_lines(body: str) -> tuple[list[str], int]:
    """Drop empty / punctuation-only lines and collapse consecutive repeats.
    Returns (lines, how many lines were dropped as repeats)."""
    out: list[str] = []
    dropped = 0
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not _HAS_WORD.search(line):  # "- -", "•", "..." — filler, and a sign of a loop
            dropped += 1
            continue
        norm = line.lstrip("-•* ").strip().lower()
        if out and out[-1].lstrip("-•* ").strip().lower() == norm:
            dropped += 1
            continue
        out.append(line)
    return out, dropped


def parse_vlm(text: str) -> dict:
    body, _, desc = text.partition("DESCRIPTION:")
    lines, dropped = _clean_lines(body)
    degenerate = dropped >= 5 or (len(lines) > 40 and len(set(l.lower() for l in lines)) < len(lines) / 2)
    verbatim = "\n".join(lines)
    desc = desc.strip()
    if degenerate:
        verbatim = (verbatim + "\n" if verbatim else "") + "[illegible]"
        desc = (DEGENERATE_NOTE + " " + desc).strip()
    return {
        "verbatim_text": verbatim,
        "description": desc,
        "illegible_count": len(_ILLEGIBLE.findall(verbatim)),
        "degenerate": degenerate,
    }


def run(session, job_id: int, files: list[int] | None = None) -> dict:
    report: dict = {"files": []}
    q = session.query(SourceFile).filter_by(job_id=job_id, kind="image")
    if files:
        q = q.filter(SourceFile.id.in_(files))
    for sf in q.all():
        entry = {"file_id": sf.id, "filename": sf.filename}
        if not ai_allowed(sf):
            entry["skipped"] = why_not(sf)
            report["files"].append(entry)
            continue
        img = Path(sf.provenance.get("ingested_path") or sf.path)
        raw = router.call(
            session, job_id=job_id, stage=3, level=sf.level,
            purpose="artefact-verbatim" + ("-l2-local-human-check" if sf.level == 2 else ""),
            prompt=PROMPT_VERBATIM, system=SYSTEM, images=[img], redacted=True, max_tokens=MAX_TOKENS,
        )
        parsed = parse_vlm(raw)
        fields = {k: parsed[k] for k in ("verbatim_text", "description", "illegible_count")}
        existing = session.query(Artefact).filter_by(file_id=sf.id).one_or_none()
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            session.add(Artefact(file_id=sf.id, **fields))
        entry.update(parsed)
        report["files"].append(entry)
    job = session.get(Job, job_id)
    job.status = "stage3:done"
    session.flush()
    return report
