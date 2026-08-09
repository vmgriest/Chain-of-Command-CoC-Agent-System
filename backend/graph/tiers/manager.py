"""Tier 2 — Department Manager.  LOCAL TOOLS ONLY, no external MCP.

The first tier that can look things up: RAG over company documents, scraping of
allowlisted domains, and sandboxed code execution.

Capabilities: local tool calling, code sandbox execution, structured output.
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
You can search the company knowledge base and read pages on the company's own
domains. You cannot search the open web, and you have no access to external
systems. When a question needs live external data, escalate to the VP.
"""


def build(model_id: str) -> CompiledStateGraph:
    """build_tier(Tier.MANAGER, persona, model_id, tools=stub_tools(), ...)
    TODO(M2): swap stub_tools() for real_tools()."""
    persona = get_config().personas.manager
    return build_tier(Tier.MANAGER, persona, model_id, stub_tools(), CAPABILITY_DESCRIPTION)


def stub_tools() -> list[BaseTool]:
    """Obviously-fake tools so the tool-calling plumbing is exercised in the
    vertical slice before RAG exists.

      lookup_order(order_id)   -> hardcoded fake order
      check_policy(topic)      -> hardcoded fake policy text

    The fakeness is visible in the returned data ("STUB:") so a demo never
    accidentally passes off stub output as real.
    """
    from langchain_core.tools import tool

    @tool
    def lookup_order(order_id: str) -> str:
        """Look up an order by its order ID and return its status."""
        return (
            f"STUB: order {order_id} — status: shipped, carrier: FakeShip, "
            f"eta: 3 business days. (This is placeholder data; real order lookup "
            f"lands in M2.)"
        )

    @tool
    def check_policy(topic: str) -> str:
        """Look up the company policy on a given topic (e.g. 'returns', 'warranty')."""
        return (
            f"STUB: policy on {topic!r} — standard 30-day window applies. "
            f"(This is placeholder data; real policy RAG lands in M2.)"
        )

    return [lookup_order, check_policy]


def real_tools() -> list[BaseTool]:
    """TODO(M2): the real set.

      rag_search(query)  -> backend.rag.retriever, returns passages WITH citations
      scrape_url(url)    -> allowlisted domains only (company.domain + crawl_urls)
      run_code(snippet)  -> backend.mcp.sandbox, Docker, no network, resource caps

    scrape_url's allowlist is a security boundary, not a convenience — an agent
    that fetches arbitrary URLs is an SSRF vector.
    """
    raise NotImplementedError


# TODO(M2): structured output on Manager responses so the CEO tier can consume
#   typed data rather than re-parsing prose.

_ = Tier  # staged for the implementation above
