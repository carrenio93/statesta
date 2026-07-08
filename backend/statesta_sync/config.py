"""Configuration loader.

Reads the two secrets the sync worker needs from `backend/.env`:
  - DATABASE_URL       (Supabase Postgres connection string)
  - API_FOOTBALL_KEY   (API-Football / api-sports.io key)

Rule (CLAUDE.md): secrets are read from .env only and NEVER hardcoded. If either
secret is missing we fail loudly, naming exactly which one — we never invent a value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# backend/.env  (this file is backend/statesta_sync/config.py -> parents[1] == backend/)
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class ConfigError(RuntimeError):
    """Raised when required configuration/secrets are missing or malformed."""


@dataclass(frozen=True)
class Config:
    """Validated runtime configuration. Both fields are guaranteed non-empty."""

    database_url: str
    api_football_key: str


def load_config() -> Config:
    """Load and validate secrets from backend/.env.

    Raises ConfigError (naming the missing key) if DATABASE_URL or
    API_FOOTBALL_KEY is absent, so callers fail fast with a clear message.
    """
    # Load backend/.env if present. Real env vars already set in the shell win
    # (override=False) so deployment can inject secrets without a file.
    load_dotenv(dotenv_path=ENV_PATH, override=False)

    database_url = (os.environ.get("DATABASE_URL") or "").strip()
    api_football_key = (os.environ.get("API_FOOTBALL_KEY") or "").strip()

    missing = []
    if not database_url:
        missing.append("DATABASE_URL")
    if not api_football_key:
        missing.append("API_FOOTBALL_KEY")

    if missing:
        raise ConfigError(
            "Missing required secret(s): "
            + ", ".join(missing)
            + f".\nAdd them to {ENV_PATH} (copy backend/.env.example to backend/.env "
            "and fill in the values). Secrets are never hardcoded or guessed."
        )

    return Config(database_url=database_url, api_football_key=api_football_key)
