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
    """build_tier(Tier.MANAGER, persona, model_id, tools=real_tools(), ...)"""
    persona = get_config().personas.manager
    return build_tier(Tier.MANAGER, persona, model_id, real_tools(), CAPABILITY_DESCRIPTION)


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


def allowed_scrape_domains() -> set[str]:
    """company.domain plus every crawl_urls host — the same allowlist the
    ingest crawler respects, so a live scrape and an ingested page are held to
    the same boundary."""
    from urllib.parse import urlparse

    config = get_config()
    return {config.company.domain} | {urlparse(str(u)).netloc for u in config.knowledge.crawl_urls}


async def rag_search_impl(query: str) -> str:
    """Search the company knowledge base (documents and ingested pages) for
    passages relevant to the query. Always cite results using their [n] marker
    and source. An empty result means the knowledge base does not cover this
    — do not answer from general knowledge in that case."""
    from backend.rag.retriever import format_for_agent, search

    collection = get_config().knowledge.qdrant_collection
    passages = await search(query, collection)
    return format_for_agent(passages)


async def scrape_url_impl(url: str) -> str:
    """Fetch and read a page from the company's own website or documentation.
    Only pages on the company's allowlisted domains are reachable — this
    cannot be used to fetch arbitrary external URLs."""
    from urllib.parse import urlparse

    import httpx

    from backend.rag.ingest import extract_page

    allowed = allowed_scrape_domains()
    if urlparse(url).netloc not in allowed:
        return f"Refused: {url!r} is not on an allowlisted domain ({sorted(allowed)})."

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            # Refuse a redirect that left the allowlist — following it is the
            # same SSRF hole with an extra step.
            if urlparse(str(response.url)).netloc not in allowed:
                return f"Refused: {url!r} redirected off the allowlist."
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Could not fetch {url!r}: {exc}"

    text, _links = extract_page(response.text, url)
    return text[:4000]


async def run_code_impl(snippet: str, language: str = "python") -> str:
    """Run a short code snippet in a sandboxed, network-isolated environment —
    useful for calculations, unit conversions, or data manipulation. There is
    no access to company systems or the internet from inside the sandbox."""
    from backend.mcp.sandbox import run_sandboxed_code

    return await run_sandboxed_code(snippet, language)


def real_tools() -> list[BaseTool]:
    """The real set, as LangChain tools bound to the Manager's own loop.

      rag_search(query)  -> backend.rag.retriever, returns passages WITH citations
      scrape_url(url)    -> allowlisted domains only (company.domain + crawl_urls)
      run_code(snippet)  -> backend.mcp.sandbox, Docker, no network, resource caps

    scrape_url's allowlist is a security boundary, not a convenience — an agent
    that fetches arbitrary URLs is an SSRF vector.

    The *_impl functions above are the single source of truth — the same
    implementations are exposed over MCP by backend/mcp/internal_server.py, so
    a Manager-tier tool call and an MCP tool call behave identically.
    """
    from langchain_core.tools import tool

    return [
        tool("rag_search")(rag_search_impl),
        tool("scrape_url")(scrape_url_impl),
        tool("run_code")(run_code_impl),
    ]


# TODO(M2+): structured output on Manager responses so the CEO tier can consume
#   typed data rather than re-parsing prose.

_ = Tier  # staged for the implementation above
