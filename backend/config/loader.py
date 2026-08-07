"""Load, validate, and cache company_config.json.

Loaded once at process start. Every other module reads config through
`get_config()` rather than re-reading the file, so a running process always sees
one consistent configuration.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from backend.config.schema import CompanyConfig

DEFAULT_CONFIG_PATH = Path("company_config.json")


class ConfigError(RuntimeError):
    """Raised when the config is missing, malformed, or fails validation.

    Should always name the offending key and what was expected — this is the
    error a company sees on their first boot.
    """


def load_config(path: Path | None = None) -> CompanyConfig:
    """TODO(M1): read JSON from `path` (or COMPANY_CONFIG_PATH env, or the default).

    Steps:
      1. Resolve the path; raise ConfigError with a pointer to
         company_config.example.json if it does not exist.
      2. Parse JSON; wrap JSONDecodeError in ConfigError with line/column.
      3. Strip the `_comment` key (see the note in schema.CompanyConfig).
      4. Validate into CompanyConfig; convert ValidationError into a ConfigError
         that reads like advice, not a stack trace.
    """
    raise NotImplementedError


@lru_cache(maxsize=1)
def get_config() -> CompanyConfig:
    """TODO(M1): cached accessor used everywhere else in the codebase.

    TODO(M5): config hot reload — expose reload_config() that clears this cache
    and re-runs the MCP registry wiring. Note that changing model ids mid-session
    would swap an agent's brain underneath a live conversation; decide whether
    reload applies to new sessions only.
    """
    raise NotImplementedError


def config_path_from_env() -> Path:
    """TODO(M1): read COMPANY_CONFIG_PATH, fall back to DEFAULT_CONFIG_PATH."""
    raise NotImplementedError


# TODO(M0): startup_checks(config) -> list[str]
#   Non-fatal warnings surfaced at boot: models not pulled in Ollama, document
#   paths that do not exist, MCP binaries not on PATH. Better to warn loudly at
#   startup than to fail on a customer's third message.
_ = (os, json)  # imports staged for the implementations above
