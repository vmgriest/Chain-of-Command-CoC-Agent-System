"""Schema-simplifying tool wrapper.

Some MCP tools expose far more parameters than a model needs to decide on
for an ordinary call — Tavily's tavily_search has 14, most optional and some
fiddly (e.g. `topic` is JSON-Schema `const: "general"`, not a free string).

Found live: llama3.2:latest kept passing topic="" instead of omitting the
field or using the literal constant, failing Tavily's own schema validation
on every attempt. The model then answered from its own training data rather
than reporting the search failure, which surfaced further up the chain as
"answered correctly but escalated anyway" — backend/graph/tiers/ceo.py's
verdict step correctly saw a failed tool call and treated the turn as
unresolved; the tool call itself was the actual failure.

Reducing what the model has to decide reduces what it can get wrong: strip
any tool's schema down to just its REQUIRED parameters before it's bound to
a model. Fields dropped this way are never sent in the underlying call at
all, so the server applies whatever default it already declares for
them — this doesn't re-implement a tool's defaults, it just stops asking a
small model to make choices it doesn't need to make.

A no-op for a tool with no optional parameters to hide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


def simplify_to_required_args(raw_tool: BaseTool) -> BaseTool:
    """Return a version of `raw_tool` whose visible schema is only its
    required parameters, calling through to `raw_tool` itself with just
    those args when invoked. Returns `raw_tool` unchanged if its schema
    isn't a plain JSON-Schema dict, or has no optional fields to strip."""
    schema = getattr(raw_tool, "args_schema", None)
    if not isinstance(schema, dict):
        return raw_tool

    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    if len(required) >= len(properties):
        return raw_tool

    from langchain_core.tools import StructuredTool

    simplified_schema = {
        "type": "object",
        "properties": {name: properties[name] for name in required if name in properties},
        "required": list(required),
    }

    async def _call(**kwargs: object) -> object:
        return await raw_tool.ainvoke(kwargs)

    return StructuredTool.from_function(
        coroutine=_call,
        name=raw_tool.name,
        description=raw_tool.description,
        args_schema=simplified_schema,
    )
