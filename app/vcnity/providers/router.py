"""The one door every model call goes through.

    Level 3  → Level3NoAI, before any provider is chosen. No exceptions.
    Level 2  → local only, and only redacted text.
    Level 1  → local by default; hosted only if allowed AND configured
               (it is not configured — HostedStub refuses).

Every call that goes through writes an `ai_calls` row, so the §5 zero is a
count, not a claim.
"""
from __future__ import annotations

from pathlib import Path

from ..audit import record_call
from ..config import settings
from .base import Provider
from .hosted_stub import HostedRefused, HostedStub  # noqa: F401  (re-exported)
from .ollama_local import OllamaProvider


class Level3NoAI(PermissionError):
    """Raised when anything tries to send Level 3 material to a model."""


class UnredactedLevel2(PermissionError):
    """Raised when Level 2 material reaches the router without redaction."""


def _local(model: str | None = None) -> Provider:
    return OllamaProvider(model or settings.ollama_model)


def get_provider(level: int, *, redacted: bool = False, model: str | None = None) -> Provider:
    if level >= 3:
        raise Level3NoAI("Level 3 material never reaches AI (PRD §4 sensitivity table)")
    if level == 2:
        if not redacted:
            raise UnredactedLevel2("Level 2 material must be redacted before any model sees it")
        return _local(model)
    if settings.allow_hosted:
        return HostedStub()
    return _local(model)


def call(
    session,
    *,
    job_id: int,
    stage: int,
    level: int,
    purpose: str,
    prompt: str,
    system: str = "",
    images: list[Path] | None = None,
    json_mode: bool = False,
    redacted: bool = False,
    max_tokens: int = 2000,
    model: str | None = None,
) -> str:
    provider = get_provider(level, redacted=redacted, model=model)
    out = provider.complete(prompt, system=system, images=images, json_mode=json_mode, max_tokens=max_tokens)
    record_call(
        session,
        job_id=job_id,
        stage=stage,
        provider=provider.name,
        is_local=provider.is_local,
        level=level,
        model=provider.model,
        purpose=purpose,
    )
    return out
