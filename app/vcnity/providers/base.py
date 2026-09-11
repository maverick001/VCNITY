from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Provider(ABC):
    """Anything that can complete a prompt. `is_local` is the property the
    router relies on; a provider that lies about it defeats the whole point."""

    name: str
    is_local: bool
    model: str

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str = "",
        images: list[Path] | None = None,
        json_mode: bool = False,
    ) -> str: ...
