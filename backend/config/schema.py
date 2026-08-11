"""Pydantic schema for company_config.json.

This is the plug-and-play surface: a company supplies one JSON file and gets a
working escalation chain. Validation is strict and happens at load time — a bad
config should fail loudly at startup, never halfway through a customer conversation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Literal

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


ORDER: list[Tier] = [Tier.FRONT_DESK, Tier.MANAGER, Tier.VICE_PRESIDENT, Tier.CEO]


def next_tier(tier: Tier) -> Tier | None:
    """The tier one rung up, or None if already at the top (CEO)."""
    idx = ORDER.index(tier)
    if idx + 1 >= len(ORDER):
        return None
    return ORDER[idx + 1]


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

    @field_validator("domain")
    @classmethod
    def _domain_is_bare(cls, v: str) -> str:
        """`domain` is the allowlist root for scrape_url() and the crawler — it
        must be a bare hostname, not a URL, or a naive `netloc == domain` check
        elsewhere would never match."""
        if v != v.strip() or "://" in v or "/" in v or v == "":
            msg = f"company.domain must be a bare hostname (e.g. 'acme.com'), got {v!r}"
            raise ValueError(msg)
        return v


class Persona(BaseModel):
    """A tier's public identity. `name` is what the agent introduces itself as;
    companies set their real CEO's name here. `theme` keys into the frontend's
    theme registry (frontend/src/themes/index.ts)."""

    name: str
    title: str
    theme: str = "slate"

    # Known theme set is shared with frontend/src/themes/index.ts THEMES keys.
    # Kept as a soft check (warn via ValueError) rather than importing the
    # frontend module — the two are mirrored by convention, checked here.
    KNOWN_THEMES: ClassVar[frozenset[str]] = frozenset({"slate", "amber", "indigo", "obsidian"})

    @field_validator("theme")
    @classmethod
    def _theme_is_known(cls, v: str) -> str:
        if v not in cls.KNOWN_THEMES:
            msg = f"Unknown theme {v!r}. Known themes: {sorted(cls.KNOWN_THEMES)}"
            raise ValueError(msg)
        return v


class PersonaSet(BaseModel):
    """One persona per tier. All four required — there is no default persona."""

    front_desk: Persona
    manager: Persona
    vice_president: Persona
    ceo: Persona

    def get(self, tier: Tier) -> Persona:
        return getattr(self, tier.value)  # type: ignore[no-any-return]


class ModelSet(BaseModel):
    """Ollama model ids per tier. Sized up the ladder: the Front Desk handles the
    bulk of traffic and should be the cheapest model that can triage reliably."""

    front_desk: str
    manager: str
    vice_president: str
    ceo: str
    embedding: str = "nomic-embed-text"

    def get(self, tier: Tier) -> str:
        return getattr(self, tier.value)  # type: ignore[no-any-return]


class KnowledgeConfig(BaseModel):
    """RAG sources. Files, directories, and URLs to crawl. Consumed by
    backend/rag/ingest.py; unused until M2."""

    documents: list[str] = Field(default_factory=list)
    crawl_urls: list[HttpUrl] = Field(default_factory=list)
    qdrant_collection: str

    # Missing document paths are a WARNING, not a load-time failure — see
    # backend/config/loader.py::startup_checks. A company config authored before
    # the docs are dropped in place should still boot; ingest.py's load_path()
    # also warns and skips rather than raising, for the same reason.


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

    # Environment variables passed to a spawned stdio server (e.g. an API key
    # a third-party MCP server needs). Values support `${VAR_NAME}` to
    # reference the HOST's actual environment (see .env / .env.example) — a
    # real secret should never sit in company_config.json directly, same
    # reasoning SMTP_PASSWORD etc. live in .env and not here. Resolved at
    # spawn time in backend/mcp/sandbox.py; a reference to an unset host var
    # warns and is dropped rather than failing startup — that server just
    # won't authenticate, same as any other single-server failure this app
    # tolerates.
    env: dict[str, str] = Field(default_factory=dict)

    # HTTP headers sent to an http-transport server (e.g. an auth header, or
    # Tavily's keyless-access header). Same `${VAR_NAME}` host-environment
    # resolution as `env` above, and resolved the same way
    # (backend/mcp/sandbox.resolve_env — the function isn't stdio-specific
    # despite its module, it's just "expand ${VAR} against os.environ").
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def _command_is_allowlisted(cls, v: str | None) -> str | None:
        """Reject anything outside ALLOWED_STDIO_BINARIES.

        This is the check that makes `"command": "bash"` fail at startup. It is
        a usability check, not the security boundary — spawn-time enforcement
        in backend/mcp/sandbox.py is what actually stops process creation.
        """
        if v is not None and v not in ALLOWED_STDIO_BINARIES:
            msg = (
                f"stdio command {v!r} is not allowlisted. "
                f"Allowed binaries: {sorted(ALLOWED_STDIO_BINARIES)}"
            )
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _transport_requires_matching_field(self) -> MCPServerConfig:
        """stdio requires `command`; http requires `url`. Reject configs that
        set both, or neither, for the declared transport."""
        if self.transport == "stdio":
            if self.command is None:
                msg = f"MCP server {self.name!r}: transport 'stdio' requires 'command'"
                raise ValueError(msg)
            if self.url is not None:
                msg = f"MCP server {self.name!r}: transport 'stdio' must not set 'url'"
                raise ValueError(msg)
        elif self.transport == "http":
            if self.url is None:
                msg = f"MCP server {self.name!r}: transport 'http' requires 'url'"
                raise ValueError(msg)
            if self.command is not None:
                msg = f"MCP server {self.name!r}: transport 'http' must not set 'command'"
                raise ValueError(msg)
        return self


class MCPServers(BaseModel):
    """Internal (first-party) vs external (third-party) servers.

    The split is organizational, not a security boundary — the security boundary
    is the sandbox in backend/mcp/sandbox.py, applied to both.
    """

    internal: list[MCPServerConfig] = Field(default_factory=list)
    external: list[MCPServerConfig] = Field(default_factory=list)

    def all_servers(self) -> list[MCPServerConfig]:
        return [*self.internal, *self.external]

    def servers_for_tier(self, tier: Tier) -> list[MCPServerConfig]:
        return [s for s in self.all_servers() if tier in s.tiers]

    @model_validator(mode="after")
    def _names_are_unique(self) -> MCPServers:
        names = [s.name for s in self.all_servers()]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            msg = f"MCP server names must be unique across internal+external: {sorted(dupes)}"
            raise ValueError(msg)
        return self


class HumanAdmin(BaseModel):
    """Where the CEO tier reaches a person. At least one channel must be set,
    or CEO escalation has nowhere to go."""

    email: str | None = None
    scheduling_link: HttpUrl | None = None

    @model_validator(mode="after")
    def _at_least_one_channel(self) -> HumanAdmin:
        if self.email is None and self.scheduling_link is None:
            msg = (
                "human_admin needs at least one channel (email or "
                "scheduling_link) — CEO escalation would otherwise have nowhere to go"
            )
            raise ValueError(msg)
        return self


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
        """Reject any MCP server listing `front_desk` in its `tiers`.

        The Front Desk having an EMPTY tool registry — not a filtered one — is a
        core invariant of the design. Enforce it at config load so a company
        cannot accidentally opt out of it.
        """
        offenders = [s.name for s in self.mcp_servers.all_servers() if Tier.FRONT_DESK in s.tiers]
        if offenders:
            msg = (
                f"front_desk must never receive MCP tools (invariant), but "
                f"these servers list it in 'tiers': {offenders}"
            )
            raise ValueError(msg)
        return self
