"""Stage 7 — Security Check (PRD §4: "Could anyone be identified?"). Flags themes that come from very few
people, and anything that gives someone away. The analyst decides what to cut,
and writes down why.

`small_n`: fewer than settings.small_n people behind the theme (PRD A11), by the
analyst's own count (PRD A6) — the app can't tell one person from another across
recordings, so it doesn't try.
`pii`: personal detail survived into what downstream stages see (a phone, email,
address, or a known name), or the local model spots identifying detail. A theme
written from Level 3 material is always flagged: its wording is checked by hand.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import selectinload

from ..config import settings
from ..models import IdentifyFlag, Job, Pseudonym, Theme, ThemeQuote
from ..providers import router
from ..redact import redact
from ..wordlist import person_names
from .s8_report import INCLUDED

SYSTEM = "You check whether text could identify a real person. Answer only from the text."
PROMPT = (
    "QUOTES:\n{quotes}\n\nCould any of these quotes let a reader work out who said it, or who it is about — "
    "a name, a job title plus a place, a rare characteristic, a specific event with few witnesses? "
    "Return JSON: {{\"identifying\": true or false, \"why\": \"short reason or empty\"}}."
)


def uncounted(session, job_id: int) -> list[str]:
    """Signed-off themes the analyst hasn't counted people for yet."""
    return [label for (label,) in session.query(Theme.label).filter(
        Theme.job_id == job_id, Theme.status.in_(INCLUDED), Theme.people_count.is_(None))]


def run(session, job_id: int) -> list[IdentifyFlag]:
    names = person_names(settings.wordlist_path) + [p.real for p in session.query(Pseudonym).filter_by(job_id=job_id)]
    flags: list[IdentifyFlag] = []
    themes = (session.query(Theme).filter(Theme.job_id == job_id, Theme.status.in_(INCLUDED))
              .options(selectinload(Theme.quotes).selectinload(ThemeQuote.unit)).all())
    for t in themes:
        # don't duplicate open flags on a re-run
        session.query(IdentifyFlag).filter_by(theme_id=t.id, decision=None).delete(synchronize_session=False)
        count = t.people_count if t.people_count is not None else 0
        if count < settings.small_n:
            f = IdentifyFlag(theme_id=t.id, kind="small_n",
                             detail=f"{count} person(s) behind this theme by the analyst's count; "
                                    f"rule is at least {settings.small_n}")
            session.add(f); flags.append(f)
        if t.from_level3:
            f = IdentifyFlag(theme_id=t.id, kind="pii",
                             detail="written from Level 3 material — check by hand that the wording names or "
                                    "gives no one away")
            session.add(f); flags.append(f)
            continue
        # What downstream stages and the report see: the swapped text for Level 2, the raw text for Level 1.
        quotes = [tq.unit.redacted_text for tq in t.quotes if not tq.unit.excluded]
        leaked = [q for q in quotes if redact(q, names) != q]
        why = ""
        if not quotes:
            pass  # an agreed theme nothing was sorted into: small_n already caught it
        elif leaked:
            why = f"redactor found personal detail in {len(leaked)} quote(s)"
        else:
            raw = router.call(session, job_id=job_id, stage=7, level=t.level, purpose="identifiability-scan",
                              prompt=PROMPT.format(quotes="\n".join(f"- {q}" for q in quotes)),
                              system=SYSTEM, json_mode=True, redacted=True)
            try:
                data = json.loads(raw)
                if data.get("identifying"):
                    why = f"model: {data.get('why', '')}".strip()
            except (json.JSONDecodeError, AttributeError):
                why = "model gave no readable verdict — a person should look"
        if why:
            f = IdentifyFlag(theme_id=t.id, kind="pii", detail=why)
            session.add(f); flags.append(f)
    job = session.get(Job, job_id)
    job.status = "stage7:flagged" if flags else "stage7:done"
    session.flush()
    return flags


def decide(session, flag_id: int, decision: str, *, reason: str) -> IdentifyFlag:
    f = session.get(IdentifyFlag, flag_id)
    if f is None:
        raise KeyError(flag_id)
    if decision not in ("keep", "cut"):
        raise ValueError("decision must be keep or cut")
    if not reason or not reason.strip():
        raise ValueError("the analyst must write down why (PRD §4 stage 7)")
    f.decision = decision
    f.reason = reason.strip()
    if decision == "cut":
        t = session.get(Theme, f.theme_id)
        t.status = "cut"  # decided_by stays as it was: this is a safety cut, not a meaning decision
        t.review_note = (t.review_note + "\n" if t.review_note else "") + f"cut at stage 7: {f.reason}"
    session.flush()
    return f


def open_flags(session, job_id: int) -> list[IdentifyFlag]:
    return (session.query(IdentifyFlag).join(Theme, Theme.id == IdentifyFlag.theme_id)
            .filter(Theme.job_id == job_id, IdentifyFlag.decision.is_(None)).all())
