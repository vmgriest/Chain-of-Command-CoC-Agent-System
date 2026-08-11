"""MCP server registry.  (M3)

Turns company_config.json into live tool bindings, per tier, at startup.

This is what makes the pipeline plug-and-play: a company declares its servers in
config and the tools land in the right tiers with no change to orchestration code.

⚠ Tool lists are built ONCE at startup, per tier. Tools are never filtered at
  call time. A tier that was not listed in a server's `tiers` array never receives
  those tools at all — there is nothing to filter and nothing to bypass.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.config.schema import ORDER, Tier

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from backend.config.schema import CompanyConfig, MCPServerConfig

logger = logging.getLogger("coc.mcp.registry")


class MCPRegistry:
    """Owns every MCP connection for the process lifetime.

    Instantiated once in the FastAPI lifespan hook; shut down with it.
    """

    def __init__(self, config: CompanyConfig) -> None:
        self._config = config
        self._tools_by_tier: dict[Tier, list[BaseTool]] = {tier: [] for tier in ORDER}
        self._client = None  # langchain_mcp_adapters.client.MultiServerMCPClient | None
        self._server_health: dict[str, bool] = {}

    def _build_connection(self, server: MCPServerConfig) -> dict | None:
        """One server's config -> a langchain-mcp-adapters connection dict, or
        None if it must be refused before any process spawns (e.g. a
        disallowed binary or a docker-escape arg)."""
        from backend.mcp import sandbox

        if server.transport == "stdio":
            try:
                argv = sandbox.docker_argv_for_server(server)
            except sandbox.SandboxViolation:
                logger.exception(
                    "MCP server %r: refused before spawn (sandbox violation)", server.name
                )
                return None
            return {"transport": "stdio", "command": argv[0], "args": argv[1:]}

        headers = sandbox.resolve_env(server.headers)
        return {
            "transport": "streamable_http",
            "url": str(server.url),
            "headers": headers or None,
        }

    async def startup(self) -> None:
        """Connect every declared server and build the per-tier tool map.

          1. For each server in internal + external, build a connection (stdio
             -> sandboxed docker argv, http -> direct URL).
          2. Hand the whole batch to one MultiServerMCPClient.
          3. Per server, list its tools; namespace as "{server_name}.{tool_name}"
             — two servers both exposing `search` would otherwise collide.
          4. Append into the map for each tier in server.tiers.

        A failing server does not take down startup: logged loudly, marked
        unavailable, and the rest boot normally — one broken third-party server
        should not deny support to every customer.
        """
        from langchain_mcp_adapters.client import MultiServerMCPClient

        from backend.mcp.tool_simplify import simplify_to_required_args

        servers = self._config.mcp_servers.all_servers()
        connections: dict[str, dict] = {}
        for server in servers:
            connection = self._build_connection(server)
            if connection is None:
                self._server_health[server.name] = False
                continue
            connections[server.name] = connection

        if not connections:
            return

        self._client = MultiServerMCPClient(connections)

        for server in servers:
            if server.name not in connections:
                continue
            try:
                tools = await self._client.get_tools(server_name=server.name)
            except Exception as exc:  # noqa: BLE001 - one bad server must not take down startup
                # A one-line warning, not a full traceback: an MCP server being
                # unreachable (not started yet, still booting, etc.) is a
                # common, expected condition during normal dev — not something
                # that needs a stack trace every time. The full traceback is
                # still available via DEBUG if actually debugging a connection.
                logger.warning(
                    "MCP server %r unavailable (%s: %s); continuing without it",
                    server.name,
                    type(exc).__name__,
                    exc,
                )
                logger.debug("MCP server %r connection failure detail", server.name, exc_info=True)
                self._server_health[server.name] = False
                continue

            self._server_health[server.name] = True
            for raw_tool in tools:
                raw_tool.name = f"{server.name}.{raw_tool.name}"
                raw_tool = simplify_to_required_args(raw_tool)
                for tier in server.tiers:
                    # Config validation already rejects front_desk in any
                    # server's tiers[]; this is the second line of defence the
                    # invariant is worth (see tools_for_tier below).
                    if tier is Tier.FRONT_DESK:
                        continue
                    self._tools_by_tier[tier].append(raw_tool)

    def tools_for_tier(self, tier: Tier) -> list[BaseTool]:
        """The prebuilt list for `tier`. Always empty for FRONT_DESK — asserted
        here as a second line of defence; config validation already rejects a
        server that lists front_desk in its `tiers`."""
        if tier is Tier.FRONT_DESK:
            return []
        return list(self._tools_by_tier.get(tier, []))

    async def shutdown(self) -> None:
        """Close HTTP sessions, then sandbox.shutdown_all()."""
        from backend.mcp import sandbox

        if self._client is not None:
            close = getattr(self._client, "close", None)
            if close is not None:
                await close()
        await sandbox.shutdown_all()

    def health(self) -> dict[str, bool]:
        """Per-server liveness for the /api/health endpoint."""
        return dict(self._server_health)


_registry: MCPRegistry | None = None


def get_registry() -> MCPRegistry:
    """Module-level singleton, matching config.loader's shape.

    Falls back to an un-started registry (empty tool maps for every tier) if
    set_registry() hasn't run yet — e.g. a tier subgraph built directly in a
    test, or in the brief window before the FastAPI lifespan's startup()
    completes. This keeps `vice_president.build()` safely callable in
    isolation; it just returns zero MCP tools until the real registry, with
    servers actually connected, is wired in via main.py's lifespan.
    """
    global _registry
    if _registry is None:
        from backend.config.loader import get_config

        _registry = MCPRegistry(get_config())
    return _registry


def set_registry(registry: MCPRegistry) -> None:
    global _registry
    _registry = registry
