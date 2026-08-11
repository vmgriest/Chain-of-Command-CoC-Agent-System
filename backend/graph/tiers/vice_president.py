"""Tier 3 — Vice President.  INTERNAL TOOLS + EXTERNAL MCP.

Everything the Manager has, plus the outside world: external MCP servers declared
in company_config.json, connected at startup and injected here by the registry.

Capabilities: MCP, stdio transport, asyncio execution loops.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.config.loader import get_config
from backend.config.schema import Tier
from backend.graph.tiers.base import build_tier

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

CAPABILITY_DESCRIPTION = """\
You have the company knowledge base, web scraping, live web search, and any
external systems connected through MCP. If you still cannot resolve this, the
CEO can involve a human.
"""


def build(model_id: str) -> CompiledStateGraph:
    """build_tier(Tier.VICE_PRESIDENT, ..., tools=real_tools(), ...)"""
    persona = get_config().personas.vice_president
    return build_tier(Tier.VICE_PRESIDENT, persona, model_id, real_tools(), CAPABILITY_DESCRIPTION)


def real_tools() -> list[BaseTool]:
    """Everything the Manager has, plus whatever external MCP servers declare
    `vice_president` in their `tiers`. The registry builds this list once at
    startup (backend/mcp/registry.py) — the VP tier just reads it."""
    from backend.graph.tiers.manager import real_tools as manager_real_tools
    from backend.mcp.registry import get_registry

    mcp_tools = get_registry().tools_for_tier(Tier.VICE_PRESIDENT)
    return [*manager_real_tools(), *mcp_tools]


def stub_tools() -> list[BaseTool]:
    """Manager stubs plus one stub external tool (fake web_search). Kept
    around for tests that want tool-calling plumbing without a live registry."""
    from langchain_core.tools import tool

    from backend.graph.tiers.manager import stub_tools as manager_stub_tools

    @tool
    def web_search(query: str) -> str:
        """Search the live web for information not in the company knowledge base."""
        return f"STUB: web search for {query!r} — no external MCP server connected."

    return [*manager_stub_tools(), web_search]


# Concurrent tool execution: already free, from LangGraph's ToolNode — see the
# note in tiers/base.py::build_tier for the timing proof.

_ = Tier  # staged for the implementation above
