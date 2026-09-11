"""Stage 6 — Community sign-off. The community confirms, fixes, rejects, or
adds what we missed. What they say goes.

The rule as code: once `decided_by == "community"`, an analyst cannot change
the theme's status, label or summary. `AuthorityError` is raised and the API
turns it into a 409. The only later path an analyst has is stage 7's cut, for
identifiability, with a written reason.
"""
from __future__ import annotations

from ..models import Job, Review, Theme, ThemeQuote, Unit

COMMUNITY_ACTIONS = {"confirm": "confirmed", "fix": "fixed", "reject": "rejected"}


class AuthorityError(PermissionError):
    """An analyst tried to override a community decision about meaning."""


def _snapshot(t: Theme) -> dict:
    return {"label": t.label, "summary": t.summary, "status": t.status, "decided_by": t.decided_by}


def review(session, theme_id: int, *, actor_role: str, action: str,
           label: str | None = None, summary: str | None = None, note: str = "") -> Theme:
    t = session.get(Theme, theme_id)
    if t is None:
        raise KeyError(theme_id)
    if actor_role not in ("community", "analyst"):
        raise ValueError("actor_role must be community or analyst")
    before = _snapshot(t)

    if actor_role == "analyst":
        if t.decided_by == "community":
            raise AuthorityError("the community has decided this theme; the analyst cannot change it (PRD §4 note)")
        if action != "note":
            raise AuthorityError("an analyst may only add a note; confirm / fix / reject belong to the community")
        t.review_note = (t.review_note + "\n" if t.review_note else "") + f"analyst: {note}".strip()
    else:
        if action not in COMMUNITY_ACTIONS:
            raise ValueError(f"action must be one of {sorted(COMMUNITY_ACTIONS)}")
        if action == "fix":
            if label is not None and label.strip():
                t.label = label.strip()[:200]
            if summary is not None:
                t.summary = summary.strip()
        t.status = COMMUNITY_ACTIONS[action]
        t.decided_by = "community"
        if note:
            t.review_note = (t.review_note + "\n" if t.review_note else "") + f"community: {note}".strip()

    session.add(Review(theme_id=t.id, actor_role=actor_role, action=action, before=before,
                       after=_snapshot(t), note=note or ""))
    session.flush()
    return t


def add_theme(session, job_id: int, label: str, summary: str, quote_unit_ids: list[int]) -> Theme:
    """A theme the community says we missed. Still needs at least one real quote."""
    ids = [int(i) for i in quote_unit_ids]
    if not ids:
        raise ValueError("an added theme needs at least one quote behind it")
    units = session.query(Unit).filter(Unit.id.in_(ids), Unit.job_id == job_id, Unit.excluded.is_(False)).all()
    if len(units) != len(set(ids)):
        raise ValueError("one or more quotes do not exist in this job or are excluded")
    t = Theme(job_id=job_id, label=label.strip()[:200] or "Untitled theme", summary=summary.strip(),
              status="added", decided_by="community", level=max(u.level for u in units),
              n_people=len({u.speaker_key for u in units}))
    session.add(t)
    session.flush()
    for u in units:
        session.add(ThemeQuote(theme_id=t.id, unit_id=u.id))
    session.add(Review(theme_id=t.id, actor_role="community", action="add", before={}, after=_snapshot(t)))
    session.flush()
    return t


def run(session, job_id: int) -> dict:
    """Stage 6 has no AI step; as a pipeline step it just reports where sign-off stands."""
    themes = session.query(Theme).filter(Theme.job_id == job_id, Theme.status != "unsupported").all()
    by = {}
    for t in themes:
        by[t.status] = by.get(t.status, 0) + 1
    job = session.get(Job, job_id)
    job.status = "stage6:in-review"
    session.flush()
    return {"themes": len(themes), "by_status": by,
            "waiting_on_community": sum(1 for t in themes if t.decided_by is None)}
