"""backend/mcp/tool_simplify.py — schema-simplifying tool wrapper.

Regression coverage for a real bug found live: llama3.2:latest reliably
failed to call Tavily's 14-parameter tavily_search tool, tripping schema
validation on the const-constrained `topic` field (see the module docstring
in backend/mcp/tool_simplify.py for the full story). The fix strips a
tool's visible schema down to its required parameters only.
"""

from __future__ import annotations

import pytest

from backend.mcp.tool_simplify import simplify_to_required_args


class _FakeTool:
    """A minimal stand-in for a langchain_core BaseTool with a dict
    (JSON-Schema) args_schema, matching what langchain_mcp_adapters hands
    back for MCP-provided tools."""

    def __init__(self, name: str, args_schema: dict, description: str = "a tool") -> None:
        self.name = name
        self.args_schema = args_schema
        self.description = description
        self.calls: list[dict] = []

    async def ainvoke(self, kwargs: dict):
        self.calls.append(kwargs)
        return {"echo": kwargs}


TAVILY_LIKE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "search query"},
        "topic": {"type": "string", "const": "general", "default": "general"},
        "max_results": {"type": "integer", "default": 5},
        "search_depth": {"type": "string", "default": "basic"},
    },
    "required": ["query"],
}


def test_simplify_keeps_only_required_properties() -> None:
    raw = _FakeTool("web_search.tavily_search", TAVILY_LIKE_SCHEMA)
    simplified = simplify_to_required_args(raw)

    assert simplified.args_schema["properties"].keys() == {"query"}
    assert simplified.args_schema["required"] == ["query"]
    assert simplified.name == "web_search.tavily_search"


def test_simplify_preserves_name_and_description() -> None:
    raw = _FakeTool("web_search.tavily_search", TAVILY_LIKE_SCHEMA, description="Search the web.")
    simplified = simplify_to_required_args(raw)

    assert simplified.name == "web_search.tavily_search"
    assert simplified.description == "Search the web."


@pytest.mark.asyncio
async def test_simplified_tool_calls_through_with_only_provided_args() -> None:
    """Fields dropped from the visible schema must never be synthesized back
    in on call — omitted means omitted, so the underlying server applies its
    own declared default rather than us guessing one."""
    raw = _FakeTool("web_search.tavily_search", TAVILY_LIKE_SCHEMA)
    simplified = simplify_to_required_args(raw)

    result = await simplified.ainvoke({"query": "capital of France"})

    assert raw.calls == [{"query": "capital of France"}]
    assert result == {"echo": {"query": "capital of France"}}


def test_simplify_is_a_noop_when_nothing_optional_to_hide() -> None:
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    raw = _FakeTool("orders.lookup", schema)

    assert simplify_to_required_args(raw) is raw


def test_simplify_is_a_noop_for_tools_with_no_dict_args_schema() -> None:
    """A tool with no args_schema at all (e.g. a bare test double) or a
    pydantic-model schema is passed through unchanged rather than crashing —
    this must be safe to call on ANY tool from any MCP server, real or
    faked in a test."""

    class _BareTool:
        name = "bare"

    bare = _BareTool()
    assert simplify_to_required_args(bare) is bare
