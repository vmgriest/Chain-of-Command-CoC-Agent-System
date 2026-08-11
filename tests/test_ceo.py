"""CEO tier: evaluator-optimizer loop + escalate_to_human tool.  (M4)

The optimizer loop is exercised with the shared FakeLLM (see conftest.py) —
same pattern as the rest of the M1 suite. It was additionally live-verified
by hand against a real Ollama model, catching a genuinely over-promising
draft and revising it into a policy-compliant one; see CHECKLIST.md.
"""

from __future__ import annotations

import pytest


def _packet(intent: str = "Wants a refund outside the return window"):
    from backend.graph.handoff import initial_packet

    packet = initial_packet("coc_ceo_test")
    packet.customer_intent = intent
    return packet


def _passing_output_verdict():
    from backend.graph.middleware.guardrails import OutputVerdict

    return OutputVerdict(
        hallucinated_commitment=False,
        leaks_internals=False,
        unsafe_advice=False,
        reason="",
    )


# ---------------------------------------------------------------------------
# DraftEvaluation.passed
# ---------------------------------------------------------------------------


def test_draft_evaluation_passed_requires_all_four_checks() -> None:
    from backend.graph.tiers.ceo import DraftEvaluation

    all_good = DraftEvaluation(
        addresses_intent=True,
        factually_grounded=True,
        no_unbacked_promises=True,
        actionable=True,
        critique="",
    )
    assert all_good.passed

    one_bad = all_good.model_copy(update={"no_unbacked_promises": False})
    assert not one_bad.passed


# ---------------------------------------------------------------------------
# make_response_optimizer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimizer_returns_draft_unchanged_when_evaluation_passes_first_try(
    monkeypatch: pytest.MonkeyPatch, fake_llm
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.graph.middleware.guardrails import OutputVerdict
    from backend.graph.tiers.ceo import DraftEvaluation, make_response_optimizer

    fake_llm.script_structured(
        DraftEvaluation,
        DraftEvaluation(
            addresses_intent=True,
            factually_grounded=True,
            no_unbacked_promises=True,
            actionable=True,
            critique="",
        ),
    )
    fake_llm.script_structured(OutputVerdict, _passing_output_verdict())
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)

    optimizer = make_response_optimizer("llama3:8b", "Jensen Huang")
    draft = AIMessage(content="Here is our standard 30-day policy.")
    state = {"packet": _packet(), "ticket_id": "coc_ceo_test"}

    result = await optimizer(state, [HumanMessage(content="hi")], draft)

    assert result is draft  # no revision call was made


@pytest.mark.asyncio
async def test_optimizer_revises_once_then_stops_on_pass(
    monkeypatch: pytest.MonkeyPatch, fake_llm
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.graph.middleware.guardrails import OutputVerdict
    from backend.graph.tiers.ceo import DraftEvaluation, make_response_optimizer

    failing = DraftEvaluation(
        addresses_intent=True,
        factually_grounded=False,
        no_unbacked_promises=False,
        actionable=True,
        critique="Do not promise a refund outside policy.",
    )
    passing = failing.model_copy(update={"factually_grounded": True, "no_unbacked_promises": True})
    fake_llm.script_structured(DraftEvaluation, failing, passing)
    fake_llm.script_structured(OutputVerdict, _passing_output_verdict())
    fake_llm.script_text(AIMessage(content="Revised: here is our standard 30-day policy."))
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)

    optimizer = make_response_optimizer("llama3:8b", "Jensen Huang")
    draft = AIMessage(content="Sure, I'll refund you right now, no problem!")
    state = {"packet": _packet(), "ticket_id": "coc_ceo_test"}

    result = await optimizer(state, [HumanMessage(content="hi")], draft)

    assert result.content == "Revised: here is our standard 30-day policy."


@pytest.mark.asyncio
async def test_optimizer_bounded_by_max_iterations_never_raises(
    monkeypatch: pytest.MonkeyPatch, fake_llm
) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.graph.middleware.guardrails import OutputVerdict
    from backend.graph.tiers.ceo import (
        MAX_OPTIMIZE_ITERATIONS,
        DraftEvaluation,
        make_response_optimizer,
    )

    always_fails = DraftEvaluation(
        addresses_intent=False,
        factually_grounded=False,
        no_unbacked_promises=False,
        actionable=False,
        critique="Still wrong.",
    )
    # Script enough failing evaluations and revisions to run past the bound —
    # the loop must stop itself rather than exhausting the script.
    fake_llm.script_structured(DraftEvaluation, *([always_fails] * MAX_OPTIMIZE_ITERATIONS))
    fake_llm.script_structured(OutputVerdict, _passing_output_verdict())
    fake_llm.script_text(
        *[AIMessage(content=f"attempt {i}") for i in range(MAX_OPTIMIZE_ITERATIONS)]
    )
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)

    optimizer = make_response_optimizer("llama3:8b", "Jensen Huang")
    draft = AIMessage(content="original")
    state = {"packet": _packet(), "ticket_id": "coc_ceo_test"}

    result = await optimizer(
        state, [HumanMessage(content="hi")], draft
    )  # must not raise/loop forever

    assert result.content != "original"  # at least one revision happened


@pytest.mark.asyncio
async def test_optimizer_stops_at_token_budget(monkeypatch: pytest.MonkeyPatch, fake_llm) -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.graph.tiers import ceo as ceo_module

    monkeypatch.setattr(
        ceo_module, "MAX_OPTIMIZE_TOKENS", 1
    )  # any real draft exceeds this instantly
    failing = ceo_module.DraftEvaluation(
        addresses_intent=False,
        factually_grounded=False,
        no_unbacked_promises=False,
        actionable=False,
        critique="wrong",
    )
    fake_llm.script_structured(ceo_module.DraftEvaluation, failing)
    from backend.graph.middleware.guardrails import OutputVerdict

    fake_llm.script_structured(OutputVerdict, _passing_output_verdict())
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)

    optimizer = ceo_module.make_response_optimizer("llama3:8b", "Jensen Huang")
    draft = AIMessage(content="a draft long enough to exceed a 1-token budget")
    state = {"packet": _packet(), "ticket_id": "coc_ceo_test"}

    result = await optimizer(state, [HumanMessage(content="hi")], draft)

    assert result is draft  # budget hit before any revision call was scripted/consumed


# ---------------------------------------------------------------------------
# escalate_to_human tool (Command-based state update)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalate_to_human_tool_updates_state_via_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tool must give CEO-tool-initiated escalation exact parity with the
    supervisor-routed path: human_notified + channels land in graph state via
    a returned Command, not just in the tool's own return string."""
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, StateGraph
    from langgraph.prebuilt import ToolNode

    from backend.graph.handoff import initial_packet
    from backend.graph.state import CoCState
    from backend.graph.tiers.ceo import make_escalate_to_human_tool

    async def _fake_notify(_packet, _reason, _urgency, _url):
        return ["email", "scheduling"]

    monkeypatch.setattr("backend.notifications.notify_human", _fake_notify)

    graph = StateGraph(CoCState)
    graph.add_node("tools", ToolNode([make_escalate_to_human_tool()]))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    compiled = graph.compile()

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "escalate_to_human",
                "args": {"reason": "PR-sensitive dispute", "urgency": "urgent"},
                "id": "call_1",
            }
        ],
    )
    state = {
        "messages": [ai_msg],
        "packet": initial_packet("coc_tool_test"),
        "session_id": "sess-1",
    }

    result = await compiled.ainvoke(state)

    assert result["human_notified"] is True
    assert result["_last_human_escalation_channels"] == ["email", "scheduling"]
    tool_message = result["messages"][-1]
    assert "email" in tool_message.content and "scheduling" in tool_message.content


def test_ceo_real_tools_includes_escalate_to_human(config) -> None:
    from backend.graph.tiers import ceo
    from backend.mcp.registry import MCPRegistry, set_registry

    set_registry(MCPRegistry(config))
    names = {t.name for t in ceo.real_tools()}
    assert "escalate_to_human" in names
    assert {"rag_search", "scrape_url", "run_code"} <= names


@pytest.mark.asyncio
async def test_ceo_real_tools_deduplicates_mcp_tools_shared_with_vp(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """A server listing BOTH vice_president and ceo in its tiers (as
    company_config.json's internal_tools does) must not appear twice in the
    CEO's bound tool list — caught live: ceo.real_tools() used to naively
    concatenate vp_real_tools() (already carrying the VP-scoped copy) with a
    second CEO-scoped copy of the exact same tools."""

    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeClient:
        def __init__(self, connections: dict) -> None:
            self.connections = connections

        async def get_tools(self, server_name: str) -> list[_FakeTool]:
            return [_FakeTool("search"), _FakeTool("lookup")]

        async def close(self) -> None:
            pass

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", _FakeClient)

    from backend.config.schema import MCPServerConfig, Tier
    from backend.graph.tiers import ceo
    from backend.mcp.registry import MCPRegistry, set_registry

    shared_server = MCPServerConfig(
        name="shared",
        transport="http",
        url="http://localhost:9001/mcp",
        tiers=[Tier.VICE_PRESIDENT, Tier.CEO],
    )
    scoped_config = config.model_copy(
        update={
            "mcp_servers": config.mcp_servers.model_copy(
                update={"internal": [shared_server], "external": []}
            )
        }
    )
    registry = MCPRegistry(scoped_config)
    await registry.startup()
    set_registry(registry)

    names = [t.name for t in ceo.real_tools()]
    assert names.count("shared.search") == 1
    assert names.count("shared.lookup") == 1
