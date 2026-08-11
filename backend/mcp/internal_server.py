"""Internal (first-party) MCP server.  (M3)

Exposes this company's own tools over MCP so internal and external tooling
share one interface. The alternative — internal tools as plain Python
functions, external ones over MCP — means two registration paths, two error
models, and two sets of bugs.

⚠ NOT spawned via the stdio allowlist. ALLOWED_STDIO_BINARIES is
  {uvx, npx, docker} deliberately — arbitrary interpreter execution
  ("python -m ...") is exactly what that allowlist exists to prevent, and this
  server is not exempt just because it's first-party. Run it as its own
  process over streamable-HTTP instead, and declare it in company_config.json
  like any other transport: "http" server:

      uv run python -m backend.mcp.internal_server --port 9001

      "mcp_servers": {"internal": [{"name": "internal_tools", "transport": "http",
        "url": "http://localhost:9001/mcp", "tiers": ["manager", "vice_president", "ceo"]}]}

  (`--transport stdio` also works for local debugging with an MCP inspector,
  but the registry never spawns this file directly — see the note above.)
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from backend.graph.tiers.manager import rag_search_impl, run_code_impl, scrape_url_impl

server = FastMCP("coc-internal")


# --- tools ------------------------------------------------------------------
#
# rag_search / scrape_url / run_code delegate to the SAME implementations the
# Manager tier calls directly (backend/graph/tiers/manager.py) — one source of
# truth for "what these tools do," regardless of whether the caller is a local
# tier loop or an MCP client.


@server.tool()
async def rag_search(query: str) -> str:
    """Search the company knowledge base for passages relevant to the query.
    Always returns citations alongside passages."""
    return await rag_search_impl(query)


@server.tool()
async def scrape_url(url: str) -> str:
    """Fetch and read a page from the company's own allowlisted domains."""
    return await scrape_url_impl(url)


@server.tool()
async def run_code(code: str, language: str = "python") -> str:
    """Execute a short code snippet in a sandboxed, network-isolated
    environment."""
    return await run_code_impl(code, language)


# --- company-specific tools ---------------------------------------------
#
# These are the ones a real deployment replaces with calls into its own order
# management / policy systems — kept clearly separate from the generic tools
# above so the swap is obvious. Fake data is prefixed "STUB:" for the same
# reason backend/graph/tiers/manager.py's M1 stubs were: a demo should never
# accidentally pass off placeholder output as real.


@server.tool()
def lookup_order(order_id: str) -> str:
    """Look up an order by its order ID and return its status."""
    return (
        f"STUB: order {order_id} — status: shipped, carrier: FastShip Ground, "
        f"eta: 3 business days. Replace this tool with a real order-system call "
        f"before production use."
    )


@server.tool()
def check_policy(topic: str) -> str:
    """Look up the company policy on a given topic (e.g. 'returns', 'warranty')."""
    return (
        f"STUB: policy on {topic!r} not found via the order system. Use rag_search "
        f"instead — the real handbook and policy docs are ingested there."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chain of Command internal MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="streamable-http",
        help="MCP transport. streamable-http is what backend.mcp.registry connects to "
        "in normal operation; stdio is for local debugging with an MCP inspector.",
    )
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server.settings.host = args.host
    server.settings.port = args.port
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
