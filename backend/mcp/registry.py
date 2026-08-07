"""MCP server registry.  (M3)

Turns company_config.json into live tool bindings, per tier, at startup.

This is what makes the pipeline plug-and-play: a company declares its servers in
config and the tools land in the right tiers with no change to orchestration code.

⚠ Tool lists are built ONCE at startup, per tier. Tools are never filtered at
  call time. A tier that was not listed in a server's `tiers` array never receives
  those tools at all — there is nothing to filter and nothing to bypass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.config.schema import Tier

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from backend.config.schema import CompanyConfig, MCPServerConfig


class MCPRegistry:
    """Owns every MCP connection for the process lifetime.

    Instantiated once in the FastAPI lifespan hook; shut down with it.
    """

    def __init__(self, config: CompanyConfig) -> None:
        # TODO(M3): store config; init empty per-tier tool maps and a connection list.
        raise NotImplementedError

    async def startup(self) -> None:
        """TODO(M3): connect every declared server and build the per-tier tool map.

          1. For each server in internal + external:
             - stdio -> backend.mcp.sandbox.spawn_mcp_server()
             - http  -> open a session to config.url
          2. List its tools via langchain-mcp-adapters
          3. Namespace tool names as "{server_name}.{tool_name}" — two servers
             both exposing `search` would otherwise collide silently
          4. Append into the map for each tier in server.tiers

        TODO(M3): a failing server must not take down startup. Log loudly, mark
          it unavailable, and let the rest boot — one broken third-party server
          should not deny support to every customer.
        """
        raise NotImplementedError

    def tools_for_tier(self, tier: Tier) -> list[BaseTool]:
        """TODO(M3): return the prebuilt list. Empty list for FRONT_DESK, always.

        TODO(M3): assert tier is not FRONT_DESK here as a second line of defence.
          Config validation already rejects it, but this is the invariant worth
          defending twice.
        """
        raise NotImplementedError

    async def shutdown(self) -> None:
        """TODO(M3): close HTTP sessions, then sandbox.shutdown_all()."""
        raise NotImplementedError

    def health(self) -> dict[str, bool]:
        """TODO(M3): per-server liveness for the /api/health endpoint."""
        raise NotImplementedError


# TODO(M3): module-level singleton + get_registry(), matching config.loader's shape.

_ = (Tier,)  # staged for the implementations above
