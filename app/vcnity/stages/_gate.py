"""May AI touch this file? The stage-level check; the router checks again."""
from __future__ import annotations


def ai_allowed(sf) -> bool:
    if sf.level >= 3:
        return False
    if sf.level == 2 and not sf.level_confirmed_by_community:
        return False
    return True


def why_not(sf) -> str:
    if sf.level >= 3:
        return "Level 3 — hand work only, no AI"
    if sf.level == 2 and not sf.level_confirmed_by_community:
        return "Level 2 — waiting for a community reviewer to confirm the level (PRD A4)"
    return ""
