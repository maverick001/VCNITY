"""Level 2 redaction: strip names and details before any model sees the text.

This is regex plus the community word list's `@person` entries. It is not a
named-entity model; the spec says so out loud. A person checks at sign-off.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Australian mobiles/landlines with optional spaces, +61, brackets.
_PHONE = re.compile(r"(?:\+?61[\s-]?|\(?0\)?)?[2-9]\d?[\s-]?\d{3,4}[\s-]?\d{3,4}\b|\b04\d{2}[\s-]?\d{3}[\s-]?\d{3}\b")
_ADDRESS = re.compile(
    r"\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][a-z]+\s+){1,3}"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Court|Ct|Lane|Ln|Place|Pl|Parade|Pde|Crescent|Cres|Terrace|Tce)\b\.?"
)


def redact(text: str, names: list[str] | tuple[str, ...] = ()) -> str:
    out = _EMAIL.sub("[email]", text)
    out = _ADDRESS.sub("[address]", out)
    out = _PHONE.sub("[phone]", out)
    for n in sorted(set(names), key=len, reverse=True):
        if not n.strip():
            continue
        out = re.sub(rf"\b{re.escape(n)}\b", "[name]", out, flags=re.IGNORECASE)
    return out
