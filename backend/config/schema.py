"""Pydantic schema for company_config.json.

This is the plug-and-play surface: a company supplies one JSON file and gets a
working escalation chain. Validation is strict and happens at load time — a bad
config should fail loudly at startup, never halfway through a customer conversation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# ---------------------------------------------------------------------------
# Tier identity
# ---------------------------------------------------------------------------


class Tier(StrEnum):
    """The four rungs of the ladder, in escalation order.

    Order matters: the supervisor uses ORDER.index() to enforce that escalation
    is monotonic. Do not reorder without updating backend/graph/supervisor.py.
    """

    FRONT_DESK = "front_desk"
    MANAGER = "manager"
    VICE_PRESIDENT = "vice_president"
    CEO = "ceo"


# TODO(M1): ORDER = [Tier.FRONT_DESK, Tier.MANAGER, Tier.VICE_PRESIDENT, Tier.CEO]
# TODO(M1): next_tier(tier) -> Tier | None  — returns None at CEO (top of ladder).


# ---------------------------------------------------------------------------
# Security: stdio execution allowlist
# ---------------------------------------------------------------------------

# Local MCP servers are third-party code. Stdio transport may only launch these.
# Enforced here at parse time AND again at spawn time in backend/mcp/sandbox.py —
# parse-time validation is a usability check, spawn-time is the security boundary.
ALLOWED_STDIO_BINARIES: frozenset[str] = frozenset({"uvx", "npx", "docker"})


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class CompanyInfo(BaseModel):
    """Identity and support boundaries. `support_scope` feeds the Front Desk
    input guardrail — off-topic questions get declined rather than escalated."""

    name: str
    domain: str
    website: HttpUrl
    support_scope: list[str] = Field(default_factory=list)

    # TODO(M2): validator — `domain` must be bare (no scheme, no path).
    #   It is the allowlist root for scrape_url().


class Persona(BaseModel):
    """A tier's public identity. `name` is what the agent introduces itself as;
    companies set their real CEO's name here. `theme` keys into the frontend's
    theme registry (frontend/src/themes/index.ts)."""

    name: str
    title: str
    theme: str = "slate"

    # TODO(M1): validator — `theme` must exist in the known theme set.
    #   Keep the known set in one place shared with the frontend types.


class PersonaSet(BaseModel):
    """One persona per tier. All four required — there is no default persona."""

    front_desk: Persona
    manager: Persona
    vice_president: Persona
    ceo: Persona

    # TODO(M1): get(tier: Tier) -> Persona


class ModelSet(BaseModel):
    """Ollama model ids per tier. Sized up the ladder: the Front Desk handles the
    bulk of traffic and should be the cheapest model that can triage reliably."""

    front_desk: str
    manager: str
    vice_president: str
    ceo: str
    embedding: str = "nomic-embed-text"

    # TODO(M1): get(tier: Tier) -> str
    # TODO(M0): startup check — warn if a model is not present in `ollama list`
    #   rather than failing on first user message.


class KnowledgeConfig(BaseModel):
    """RAG sources. Files, directories, and URLs to crawl. Consumed by
    backend/rag/ingest.py; unused until M2."""

    documents: list[str] = Field(default_factory=list)
    crawl_urls: list[HttpUrl] = Field(default_factory=list)
    qdrant_collection: str

    # TODO(M2): validator — every path in `documents` exists and is readable.


class MCPServerConfig(BaseModel):
    """One MCP server declaration.

    stdio -> spawned as a sandboxed subprocess (see backend/mcp/sandbox.py)
    http  -> connected to over the network

    `tiers` decides which agents receive this server's tools. A tier not listed
    here never sees them — the registry builds per-tier tool lists at startup
    rather than filtering at call time.
    """

    name: str
    transport: Literal["stdio", "http"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: HttpUrl | None = None
    tiers: list[Tier]

    @field_validator("command")
    @classmethod
    def _command_is_allowlisted(cls, v: str | None) -> str | None:
        """TODO(M1): reject anything outside ALLOWED_STDIO_BINARIES.

        Raise ValueError naming the offending binary and listing what is allowed.
        This is the check that makes `"command": "bash"` fail at startup.
        """
        raise NotImplementedError

    @model_validator(mode="after")
    def _transport_requires_matching_field(self) -> MCPServerConfig:
        """TODO(M1): stdio requires `command`; http requires `url`. Reject configs
        that set both, or neither, for the declared transport."""
        raise NotImplementedError


class MCPServers(BaseModel):
    """Internal (first-party) vs external (third-party) servers.

    The split is organizational, not a security boundary — the security boundary
    is the sandbox in backend/mcp/sandbox.py, applied to both.
    """

    internal: list[MCPServerConfig] = Field(default_factory=list)
    external: list[MCPServerConfig] = Field(default_factory=list)

    # TODO(M3): all_servers() -> list[MCPServerConfig]
    # TODO(M3): servers_for_tier(tier) -> list[MCPServerConfig]
    # TODO(M3): validator — server names are unique across internal + external.


class HumanAdmin(BaseModel):
    """Where the CEO tier reaches a person. At least one channel must be set,
    or CEO escalation has nowhere to go."""

    email: str | None = None
    push_topic: str | None = None
    scheduling_link: HttpUrl | None = None

    # TODO(M4): model_validator — require at least one channel to be non-None.


class EscalationConfig(BaseModel):
    """Escalation policy.

    `require_user_consent` gates AGENT-initiated escalation only. A user asking
    for upper management is always honored immediately, regardless of this flag.
    """

    require_user_consent: bool = True
    max_attempts_per_tier: int = Field(default=3, ge=1, le=10)
    human_admin: HumanAdmin


class CompanyConfig(BaseModel):
    """Root config model. Loaded once at startup by backend/config/loader.py."""

    company: CompanyInfo
    personas: PersonaSet
    models: ModelSet
    knowledge: KnowledgeConfig
    mcp_servers: MCPServers = Field(default_factory=MCPServers)
    escalation: EscalationConfig

    model_config = {"extra": "forbid"}  # typo in a key should fail, not be ignored

    # NOTE: company_config.example.json carries a "_comment" key. Either strip it
    # in the loader or add it as an explicit ignored field — `extra: forbid`
    # rejects it as written. TODO(M1): decide which; loader-strip is cleaner.

    @model_validator(mode="after")
    def _front_desk_has_no_tools(self) -> CompanyConfig:
        """TODO(M1): reject any MCP server listing `front_desk` in its `tiers`.

        The Front Desk having an EMPTY tool registry — not a filtered one — is a
        core invariant of the design. Enforce it at config load so a company
        cannot accidentally opt out of it.
        """
        raise NotImplementedError
