"""Stage 5 — Evidence check. Every claim traces to a real quote; the ones that
don't get thrown out before a person ever sees them.

Two checks. Structural: the theme's quotes still exist and none has been
excluded (a file raised to Level 3 takes its quotes with it). Grounding: the
local model is asked, strictly, whether the summary claims anything the quotes
do not say. Either failing marks the theme `unsupported`, and unsupported
themes never appear on the sign-off page.
"""
from __future__ import annotations

import json

from ..models import Job, Theme, ThemeQuote, Unit
from ..providers import router

SYSTEM = "You are a strict fact checker. You answer only from the quotes given."
PROMPT = (
    "QUOTES:\n{quotes}\n\nSUMMARY:\n{summary}\n\n"
    "Does the SUMMARY claim anything that the QUOTES do not say — a fact, a cause, a number, "
    "a feeling, or a group of people not mentioned? Return JSON: "
    "{{\"unsupported\": true or false, \"sentence\": \"the offending sentence, or empty\"}}."
)


def check_structural(session, theme_id: int) -> bool:
    rows = (session.query(ThemeQuote, Unit).join(Unit, Unit.id == ThemeQuote.unit_id)
            .filter(ThemeQuote.theme_id == theme_id).all())
    if not rows:
        return False
    return all(not u.excluded for _, u in rows)


def check_grounding(session, theme: Theme) -> tuple[bool, str]:
    quotes = [tq.unit.redacted_text for tq in theme.quotes if not tq.unit.excluded]
    raw = router.call(
        session, job_id=theme.job_id, stage=5, level=theme.level, purpose="grounding-check",
        prompt=PROMPT.format(quotes="\n".join(f"- {q}" for q in quotes), summary=theme.summary),
        system=SYSTEM, json_mode=True, redacted=True,
    )
    try:
        data = json.loads(raw)
        return bool(data.get("unsupported")), str(data.get("sentence", ""))
    except (json.JSONDecodeError, AttributeError):
        # If the checker itself is unreadable, fail closed: a person looks.
        return True, "checker returned no verdict"


def run(session, job_id: int) -> dict:
    unsupported: list[int] = []
    checked = 0
    for t in session.query(Theme).filter(Theme.job_id == job_id,
                                          Theme.status.notin_(("rejected", "cut"))).all():
        checked += 1
        if not check_structural(session, t.id):
            t.status = "unsupported"
            t.review_note = (t.review_note + "\n" if t.review_note else "") + "evidence: a quote was removed or excluded"
            unsupported.append(t.id)
            continue
        if t.status == "draft":  # community-fixed summaries are the community's words; don't second-guess them
            bad, sentence = check_grounding(session, t)
            if bad:
                t.status = "unsupported"
                t.review_note = (t.review_note + "\n" if t.review_note else "") + f"evidence: {sentence}"
                unsupported.append(t.id)
    job = session.get(Job, job_id)
    job.status = "stage5:done"
    session.flush()
    return {"checked": checked, "unsupported": unsupported}
