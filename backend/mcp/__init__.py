"""MCP integration: internal server, registry, sandboxing.  (M3)

⚠ NAMING: this package is `backend.mcp`, which shadows the PyPI `mcp` package
  for relative imports. Python 3 uses absolute imports by default so
  `import mcp` inside these modules still resolves to site-packages — but keep
  every import here absolute and explicit, and never add `from . import mcp`.
"""
