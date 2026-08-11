"""Load, validate, and cache company_config.json.

Loaded once at process start. Every other module reads config through
`get_config()` rather than re-reading the file, so a running process always sees
one consistent configuration.
"""

from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from backend.config.schema import CompanyConfig

DEFAULT_CONFIG_PATH = Path("company_config.json")
EXAMPLE_CONFIG_PATH = Path("company_config.example.json")


class ConfigError(RuntimeError):
    """Raised when the config is missing, malformed, or fails validation.

    Should always name the offending key and what was expected — this is the
    error a company sees on their first boot.
    """


def config_path_from_env() -> Path:
    """Read COMPANY_CONFIG_PATH, fall back to DEFAULT_CONFIG_PATH."""
    raw = os.environ.get("COMPANY_CONFIG_PATH")
    return Path(raw) if raw else DEFAULT_CONFIG_PATH


def load_config(path: Path | None = None) -> CompanyConfig:
    """Read JSON from `path` (or COMPANY_CONFIG_PATH env, or the default).

    Steps:
      1. Resolve the path; raise ConfigError with a pointer to
         company_config.example.json if it does not exist.
      2. Parse JSON; wrap JSONDecodeError in ConfigError with line/column.
      3. Strip the `_comment` key (see the note in schema.CompanyConfig).
      4. Validate into CompanyConfig; convert ValidationError into a ConfigError
         that reads like advice, not a stack trace.
    """
    resolved = path if path is not None else config_path_from_env()

    if not resolved.exists():
        msg = (
            f"Company config not found at {resolved!s}. "
            f"Copy {EXAMPLE_CONFIG_PATH!s} to {resolved!s} and edit it, "
            f"or set COMPANY_CONFIG_PATH to point elsewhere."
        )
        raise ConfigError(msg)

    raw_text = resolved.read_text(encoding="utf-8")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = (
            f"Could not parse {resolved!s} as JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        )
        raise ConfigError(msg) from exc

    if isinstance(raw, dict):
        raw.pop("_comment", None)

    try:
        return CompanyConfig.model_validate(raw)
    except ValidationError as exc:
        lines = [f"Invalid config at {resolved!s}:"]
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            lines.append(f"  - {loc}: {err['msg']}")
        raise ConfigError("\n".join(lines)) from exc


@lru_cache(maxsize=1)
def get_config() -> CompanyConfig:
    """Cached accessor used everywhere else in the codebase."""
    return load_config()


def reload_config(path: Path | None = None) -> CompanyConfig:
    """Re-read and re-validate company_config.json without restarting the
    process, swapping the cached config atomically: reload_config() either
    fully succeeds or leaves the previous (still valid) config in place —
    never a half-applied state a customer mid-conversation could be served
    against. Raises ConfigError on an invalid file, same as load_config().

    What picks this up immediately, with NO graph rebuild required — every
    call site below reads get_config() fresh, per-call, not once at startup:
      - backend/graph/tiers/manager.py's tools (rag_search's qdrant_collection,
        scrape_url's domain allowlist, run_code)
      - support_scope (guardrails, the system prompt's "we handle X" line)
      - escalation policy (max_attempts_per_tier, require_user_consent)
      - human_admin channels (email/scheduling — read at the moment of an
        actual escalation, not cached anywhere)

    What does NOT take effect without a full graph rebuild (a process
    restart, in this dev-only MemorySaver setup — see the TODO on
    build_graph() about a persistent checkpointer): model ids and personas.
    Both are resolved ONCE per tier when backend/graph/supervisor.py's
    build_graph() compiles each tier's subgraph, and baked into that
    compiled graph via closures (make_model(), render_system_prompt's
    `persona` parameter). Swapping a model or persona underneath a LIVE
    conversation graph is exactly the risk this function's original TODO
    flagged — deliberately out of scope for a reload aimed at content
    changes (knowledge sources, policy, contact channels), not brain swaps.
    """
    validated = load_config(path)  # raises ConfigError; cache untouched on failure
    get_config.cache_clear()  # next get_config() call re-reads and re-caches lazily
    return validated


def startup_checks(config: CompanyConfig) -> list[str]:
    """Non-fatal warnings surfaced at boot: models not pulled in Ollama, document
    paths that do not exist, MCP binaries not on PATH. Better to warn loudly at
    startup than to fail on a customer's third message.
    """
    warnings: list[str] = []

    model_ids = {
        config.models.front_desk,
        config.models.manager,
        config.models.vice_president,
        config.models.ceo,
    }
    try:
        import ollama as ollama_client

        available = {m.model for m in ollama_client.list().models}
        for model_id in sorted(model_ids):
            if model_id not in available:
                warnings.append(
                    f"Model {model_id!r} not found via `ollama list` — pull it "
                    f"before the first customer message ({config.company.name})."
                )
    except Exception as exc:  # noqa: BLE001 - startup warning must never crash boot
        warnings.append(f"Could not reach Ollama to verify models are pulled: {exc}")

    for doc_path in config.knowledge.documents:
        if not Path(doc_path).exists():
            warnings.append(f"Knowledge document path does not exist: {doc_path}")

    for server in config.mcp_servers.all_servers():
        if server.transport == "stdio" and server.command and shutil.which(server.command) is None:
            warnings.append(
                f"MCP server {server.name!r}: binary {server.command!r} not found on PATH"
            )

    return warnings
