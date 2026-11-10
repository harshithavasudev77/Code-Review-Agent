"""Provider configuration. Credentials never enter graph state or reports."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from striprtf.striprtf import rtf_to_text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NEBIUS_BASE_URL = "https://api.tokenfactory.eu-north1.nebius.com/v1/"
DEFAULT_MODEL = "nvidia/Nemotron-3_5-Lightning"


class ConfigurationError(ValueError):
    """A configuration error safe to show in the UI."""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_key: SecretStr = Field(repr=False, exclude=True)
    key_source: str = "environment"
    model: str = DEFAULT_MODEL
    timeout_seconds: float = Field(default=90, ge=5, le=180)
    max_tokens: int = Field(default=4096, ge=256, le=8192)
    max_attempts: int = Field(default=2, ge=1, le=3)


def load_settings(project_root: Path = PROJECT_ROOT) -> Settings:
    """Use the environment, a local .env, then the supplied RTF credential."""
    values = dotenv_values(project_root / ".env")

    def option(name: str, default: str) -> str:
        return os.environ.get(name) or values.get(name) or default

    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    source = "NEBIUS_API_KEY environment variable"
    if not key:
        key = str(values.get("NEBIUS_API_KEY") or "").strip()
        source = "local .env"
    if not key:
        credential_file = project_root / "nebius-api-key.rtf"
        if credential_file.is_file() and credential_file.stat().st_size <= 16_384:
            try:
                key = rtf_to_text(credential_file.read_text(encoding="utf-8")).strip()
                source = "local credential file"
            except (OSError, UnicodeError, ValueError):
                raise ConfigurationError("Could not read the local Nebius credential file.") from None
    # Support a bare token or NEBIUS_API_KEY=<token>, without logging either.
    key = re.sub(r"^NEBIUS_API_KEY\s*[:=]\s*", "", key).strip().strip("\"'")
    if not key or any(c.isspace() for c in key):
        raise ConfigurationError(
            "Set NEBIUS_API_KEY in the environment or .env, or supply nebius-api-key.rtf."
        )
    try:
        return Settings(
            api_key=SecretStr(key),
            key_source=source,
            model=option("NEBIUS_MODEL", DEFAULT_MODEL),
            timeout_seconds=float(option("NEBIUS_TIMEOUT_SECONDS", "90")),
            max_tokens=int(option("NEBIUS_MAX_TOKENS", "4096")),
        )
    except ValueError:
        raise ConfigurationError("Invalid Nebius model, timeout, or token configuration.") from None
