"""The slot where a hosted model (TechStack: Gemini Flash for Level 1–2 drafting)
would go. It refuses every call. That is deliberate: PRD A7 says nothing goes
to a public AI service without an agreement, and there is no agreement."""
from __future__ import annotations


class HostedRefused(RuntimeError):
    pass


class HostedStub:
    name = "hosted:none"
    is_local = False
    model = "none"

    def complete(self, prompt, system="", images=None, json_mode=False, max_tokens=2000) -> str:
        raise HostedRefused("no hosted provider is configured (PRD A7 — no agreement in place)")
