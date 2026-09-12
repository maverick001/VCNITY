"""Raise a concern — one obvious way to raise something, from any stage, in
the person's own words. They describe what happened; a person sorts it.

Routing follows the PRD's table (v0.3 A13). Who actually receives a harm
report is a config value that is UNSET until the client names someone —
that is the one thing we ask for before the first pilot.
"""
from __future__ import annotations

from ..config import settings
from ..models import Concern

ROUTING: dict[str, tuple[str, int | None]] = {
    "harm": ("safety_contact", 3),
    "misuse": ("VCNITY analyst on this job", 2),
    "conduct": ("Community organisation, copied to VCNITY", 2),
    "ai_error": ("VCNITY analyst on this job", None),  # same level as the material
}


def raise_concern(session, job_id: int, *, stage: int, text: str) -> Concern:
    if not text or not text.strip():
        raise ValueError("say what happened, in your own words")
    c = Concern(job_id=job_id, stage=int(stage), text=text.strip(), status="new")
    session.add(c)
    session.flush()
    return c


def sort_concern(session, concern_id: int, category: str, material_level: int | None = None) -> Concern:
    c = session.get(Concern, concern_id)
    if c is None:
        raise KeyError(concern_id)
    if category not in ROUTING:
        raise ValueError(f"category must be one of {sorted(ROUTING)}")
    target, level = ROUTING[category]
    c.category = category
    c.routed_to = settings.safety_contact if target == "safety_contact" else target
    c.level = level if level is not None else material_level
    c.status = "routed"
    session.flush()
    return c
