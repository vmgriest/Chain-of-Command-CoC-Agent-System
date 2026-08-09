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
    """build_tier(Tier.VICE_PRESIDENT, ..., tools=stub_tools(), ...)
    TODO(M3): tools = manager.real_tools() + registry.tools_for_tier(VICE_PRESIDENT)"""
    persona = get_config().personas.vice_president
    return build_tier(Tier.VICE_PRESIDENT, persona, model_id, stub_tools(), CAPABILITY_DESCRIPTION)


def stub_tools() -> list[BaseTool]:
    """Manager stubs plus one stub external tool (fake web_search) so the M1
    slice exercises the "external tool" path before MCP exists."""
    from langchain_core.tools import tool

    from backend.graph.tiers.manager import stub_tools as manager_stub_tools

    @tool
    def web_search(query: str) -> str:
        """Search the live web for information not in the company knowledge base."""
        return (
            f"STUB: web search for {query!r} — no external MCP server connected yet. "
            f"(Real live web search lands in M3.)"
        )

    return [*manager_stub_tools(), web_search]


# TODO(M3): concurrent tool execution.
#   When the model requests several independent tool calls in one turn, run them
#   with asyncio.gather rather than sequentially. Implement in tiers/base.py
#   behind a flag so every tier benefits — do not fork the loop here.
#   Watch out: tool calls with ordering dependencies must not be parallelized.
#   Simplest safe rule for M3 — parallelize only calls to DIFFERENT tools.

_ = Tier  # staged for the implementation above
