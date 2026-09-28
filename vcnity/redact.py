"""Level 2 redaction: real names swapped for made-up ones, other details stripped,
before any model sees the text (PRD §4 sensitivity table).

Names come from the community word list's `@person` entries and from the local
model's name scan at stage 4; a person checks the result before sorting starts.
Phones, emails and street addresses are caught by regex. `redact()` is the plain
version used to spot personal detail that survived.
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

# Made-up names handed out in order. Any that is also a real name in the job is skipped.
FAKE_NAMES = ("Alex", "Sam", "Jordan", "Robin", "Casey", "Riley", "Morgan", "Jamie", "Taylor", "Quinn",
              "Avery", "Drew", "Harper", "Kai", "Reese", "Rowan", "Sage", "Emerson", "Finley", "Hayden")


def _details(text: str) -> str:
    out = _EMAIL.sub("[email]", text)
    out = _ADDRESS.sub("[address]", out)
    return _PHONE.sub("[phone]", out)


def _swap(text: str, mapping: dict[str, str]) -> str:
    for real in sorted(mapping, key=len, reverse=True):
        if real.strip():
            text = re.sub(rf"\b{re.escape(real)}\b", mapping[real], text, flags=re.IGNORECASE)
    return text


def redact(text: str, names: list[str] | tuple[str, ...] = ()) -> str:
    return _swap(_details(text), {n: "[name]" for n in names})


def pseudonymise(text: str, mapping: dict[str, str]) -> str:
    """Real names → their made-up names; phones, emails, addresses → placeholders."""
    return _swap(_details(text), mapping)


def next_fake(taken_fakes: set[str], real_names: set[str]) -> str:
    """The first made-up name not already given out and not itself a real name in the job."""
    avoid = {n.lower() for n in taken_fakes | real_names}
    for name in FAKE_NAMES:
        if name.lower() not in avoid:
            return name
    i = len(taken_fakes) + 1
    while f"person {i}" in avoid:
        i += 1
    return f"Person {i}"
