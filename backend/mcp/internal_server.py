"""Internal (first-party) MCP server.  (M3)

Exposes this company's own tools over MCP so internal and external tooling share
one interface. The alternative — internal tools as plain Python functions,
external ones over MCP — means two registration paths, two error models, and two
sets of bugs.

Run as its own process (stdio), spawned by the registry like any other server.
"""

from __future__ import annotations

# TODO(M3): from mcp.server import Server
# TODO(M3): from mcp.server.stdio import stdio_server
#   NOTE: absolute import of the PyPI `mcp` package. See the shadowing warning in
#   backend/mcp/__init__.py.

# TODO(M3): server = Server("coc-internal")


# --- tools ---------------------------------------------------------------
#
# TODO(M3): rag_search(query: str, top_k: int = 5)
#   Delegates to backend.rag.retriever. MUST return citations alongside passages
#   — an answer the agent cannot attribute is one the customer cannot verify.
#
# TODO(M3): scrape_url(url: str)
#   Allowlisted domains only (company.domain + knowledge.crawl_urls). Reject
#   everything else, including redirects that leave the allowlist — following a
#   redirect off-allowlist is the same SSRF hole with an extra step.
#
# TODO(M3): run_code(code: str, language: str = "python")
#   Delegates to backend.mcp.sandbox.run_sandboxed_code.
#
# TODO(M3): lookup_order / check_policy / account_status
#   Company-specific. These are the ones a real deployment replaces with calls
#   into its own systems — keep them clearly separated from the generic tools
#   above so the swap is obvious.


# TODO(M3): async def main() — run over stdio_server()
# TODO(M3): if __name__ == "__main__": asyncio.run(main())
#   Entry point so the registry can spawn this with `uvx` or `python -m`.
