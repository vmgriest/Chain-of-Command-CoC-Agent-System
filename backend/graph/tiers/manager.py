"""Tier 2 — Department Manager.  LOCAL TOOLS ONLY, no external MCP.

The first tier that can look things up: RAG over company documents, scraping of
allowlisted domains, and sandboxed code execution.

Capabilities: local tool calling, code sandbox execution, structured output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.config.schema import Tier

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

CAPABILITY_DESCRIPTION = """\
You can search the company knowledge base and read pages on the company's own
domains. You cannot search the open web, and you have no access to external
systems. When a question needs live external data, escalate to the VP.
"""


def build(model_id: str) -> CompiledStateGraph:
    """TODO(M1): build_tier(Tier.MANAGER, persona, model_id, tools=stub_tools(), ...)
    TODO(M2): swap stub_tools() for real_tools()."""
    raise NotImplementedError


def stub_tools() -> list[BaseTool]:
    """TODO(M1): obviously-fake tools so the tool-calling plumbing is exercised
    in the vertical slice before RAG exists.

      lookup_order(order_id)   -> hardcoded fake order
      check_policy(topic)      -> hardcoded fake policy text

    Make the fakeness visible in the returned data (e.g. "STUB:") so a demo never
    accidentally passes off stub output as real.
    """
    raise NotImplementedError


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
