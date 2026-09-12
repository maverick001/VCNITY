"""Settings for the pipeline. Everything comes from the environment or app/.env.

Nothing in here imports a web framework or a model library.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = APP_DIR.parent
load_dotenv(APP_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    home: Path
    cache_dir: Path
    pg_dir: Path
    ollama_model: str
    ollama_vision_model: str
    hf_token: str | None
    allow_hosted: bool
    small_n: int
    safety_contact: str
    api_port: int
    wordlist_path: Path


def load_settings() -> Settings:
    home = Path(os.environ.get("VCNITY_HOME", Path.home() / ".vcnity"))
    return Settings(
        data_dir=Path(os.environ.get("VCNITY_DATA_DIR", REPO_DIR / "Data" / "raw")),
        home=home,
        cache_dir=home / "cache",
        pg_dir=home / "pgdata",
        # Two different models, used at different pipeline stages. On a 16GB/no-GPU
        # laptop they must never be resident together — see providers/ollama_local.py.
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen3.5:4b"),
        ollama_vision_model=os.environ.get("OLLAMA_VISION_MODEL", "qwen3-vl:4b"),
        hf_token=os.environ.get("HF_TOKEN") or None,
        allow_hosted=os.environ.get("VCNITY_ALLOW_HOSTED", "0") == "1",
        small_n=int(os.environ.get("VCNITY_SMALL_N", "3")),
        safety_contact=os.environ.get("VCNITY_SAFETY_CONTACT") or "UNSET — see PRD A13",
        api_port=int(os.environ.get("VCNITY_API_PORT", "8100")),
        wordlist_path=Path(os.environ.get("VCNITY_WORDLIST", APP_DIR / "data" / "wordlist.txt")),
    )


settings = load_settings()
