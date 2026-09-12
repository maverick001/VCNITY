"""Stage 7 — Could anyone be identified? Flags themes that come from very few
people, and anything that gives someone away. The analyst decides what to cut,
and writes down why.

`small_n`: fewer than settings.small_n distinct people behind the theme (PRD A6).
`pii`: the redactor would change a quote (a phone, email, address, listed name
survived), or the local model spots identifying detail.
"""
from __future__ import annotations

import json

from ..config import settings
from ..models import IdentifyFlag, Job, Theme
from ..providers import router
from ..redact import redact
from ..wordlist import person_names

INCLUDED = ("confirmed", "fixed", "added")

SYSTEM = "You check whether text could identify a real person. Answer only from the text."
PROMPT = (
    "QUOTES:\n{quotes}\n\nCould any of these quotes let a reader work out who said it, or who it is about — "
    "a name, a job title plus a place, a rare characteristic, a specific event with few witnesses? "
    "Return JSON: {{\"identifying\": true or false, \"why\": \"short reason or empty\"}}."
)


def run(session, job_id: int) -> list[IdentifyFlag]:
    names = person_names(settings.wordlist_path)
    flags: list[IdentifyFlag] = []
    themes = session.query(Theme).filter(Theme.job_id == job_id, Theme.status.in_(INCLUDED)).all()
    for t in themes:
        # don't duplicate open flags on a re-run
        session.query(IdentifyFlag).filter_by(theme_id=t.id, decision=None).delete(synchronize_session=False)
        if t.n_people < settings.small_n:
            f = IdentifyFlag(theme_id=t.id, kind="small_n",
                             detail=f"{t.n_people} person(s) behind this theme; rule is at least {settings.small_n}")
            session.add(f); flags.append(f)
        quotes = [tq.unit.text for tq in t.quotes if not tq.unit.excluded]
        leaked = [q for q in quotes if redact(q, names) != q]
        why = ""
        if leaked:
            why = f"redactor found personal detail in {len(leaked)} quote(s)"
        else:
            raw = router.call(session, job_id=job_id, stage=7, level=t.level, purpose="identifiability-scan",
                              prompt=PROMPT.format(quotes="\n".join(f"- {q}" for q in
                                                                    [tq.unit.redacted_text for tq in t.quotes
                                                                     if not tq.unit.excluded])),
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
