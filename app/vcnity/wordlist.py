"""The community word list: names, slang, local place words (PRD §4 stage 2).

One term per line. `# comment` lines are ignored. A term tagged `@person`
is also treated as a personal name for redaction.
"""
from __future__ import annotations

from pathlib import Path

PERSON_TAG = "@person"


def _lines(path: Path) -> list[tuple[str, bool]]:
    path = Path(path)
    if not path.exists():
        return []
    out: list[tuple[str, bool]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        is_person = PERSON_TAG in line
        term = line.replace(PERSON_TAG, "").strip()
        if term:
            out.append((term, is_person))
    return out


def load_wordlist(path: Path) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term, _ in _lines(path):
        if term.lower() not in seen:
            seen.add(term.lower())
            result.append(term)
    return result


def person_names(path: Path) -> list[str]:
    return [t for t, p in _lines(path) if p]


def as_hotwords(words: list[str]) -> str:
    return ", ".join(words)


def save_wordlist(path: Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")
