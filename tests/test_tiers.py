"""Per-tier behaviour tests.  (M1+)"""

from __future__ import annotations

import pytest

# --- shared loop (base.py) ------------------------------------------------


def test_build_tier_with_no_tools_omits_tool_node() -> None:
    from backend.config.loader import get_config
    from backend.config.schema import Tier
    from backend.graph.tiers.base import build_tier

    persona = get_config().personas.front_desk
    compiled = build_tier(Tier.FRONT_DESK, persona, "llama3.2:latest", [], "no tools")
    assert "tools" not in compiled.get_graph().nodes


def test_build_tier_with_tools_includes_tool_node() -> None:
    from langchain_core.tools import tool

    from backend.config.loader import get_config
    from backend.config.schema import Tier
    from backend.graph.tiers.base import build_tier

    @tool
    def dummy_tool(x: str) -> str:
        """A dummy tool."""
        return x

    persona = get_config().personas.manager
    compiled = build_tier(Tier.MANAGER, persona, "llama3:8b", [dummy_tool], "has tools")
    assert "tools" in compiled.get_graph().nodes


@pytest.mark.asyncio
async def test_persona_name_comes_from_config() -> None:
    """Rename the persona; the introduction changes. Nothing hardcoded."""
    from backend.config.schema import Persona
    from backend.graph.handoff import initial_packet
    from backend.graph.tiers.base import introduce

    custom_persona = Persona(name="Zara", title="Lead Concierge", theme="slate")
    state = {"packet": initial_packet("coc_x")}
    updates = await introduce(state, custom_persona)
    text = updates["messages"][0].content
    assert "Zara" in text
    assert "Lead Concierge" in text
    assert updates["tier_just_changed"] is False


@pytest.mark.asyncio
async def test_introduction_references_customer_intent_when_known() -> None:
    from backend.config.schema import Persona
    from backend.graph.handoff import initial_packet
    from backend.graph.tiers.base import introduce

    packet = initial_packet("coc_x")
    packet.customer_intent = "SSO login is broken"
    state = {"packet": packet}
    updates = await introduce(state, Persona(name="Dwight", title="Manager", theme="amber"))
    text = updates["messages"][0].content
    assert "SSO login is broken" in text


def test_render_system_prompt_carries_ruled_out_and_facts() -> None:
    from backend.config.schema import Persona
    from backend.graph.handoff import HandoffPacket
    from backend.graph.tiers.base import render_system_prompt
    from tests.conftest import FakeLLM  # noqa: F401 - not used, keeps import style consistent

    packet = HandoffPacket(
        ticket_id="coc_x",
        customer_intent="Cannot log in",
        verified_facts=["Account #123"],
        ruled_out=["expired password"],
        escalation_reason="needs tools",
    )
    prompt = render_system_prompt(
        Persona(name="Dwight", title="Manager", theme="amber"),
        "Acme Robotics",
        ["orders"],
        "You have local tools.",
        packet,
    )
    assert "Account #123" in prompt
    assert "expired password" in prompt
    assert "Dwight" in prompt
    assert "Manager" in prompt


@pytest.mark.asyncio
async def test_verdict_node_escalation_reason_fallback_is_a_noun_phrase(monkeypatch) -> None:
    """Regression test for a real bug found live: when the model returns
    can_resolve=False with no escalation_reason, the fallback text lands
    straight in hitl.py's "I don't have {reason} from this desk." template —
    it must read as a noun phrase there, not a clause. The old fallback
    ("unable to resolve at this tier") produced the nonsensical "I don't have
    unable to resolve at this tier from this desk.", visible live in the
    escalation-consent banner."""
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.config.schema import Tier
    from backend.graph.handoff import initial_packet
    from backend.graph.tiers.base import TierVerdict, build_tier
    from tests.conftest import FakeLLM

    fake = FakeLLM()
    fake.script_text(AIMessage(content="Here is a complete, correct answer."))
    fake.script_structured(TierVerdict, TierVerdict(can_resolve=False, escalation_reason=None))
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake)

    from backend.config.loader import get_config

    persona = get_config().personas.manager
    compiled = build_tier(Tier.MANAGER, persona, "llama3.2:latest", [], "no tools")

    state = {
        "messages": [HumanMessage(content="What does error E-317 mean?")],
        "packet": initial_packet("coc_verdict_test"),
    }
    result = await compiled.ainvoke(state)

    reason = result["pending_escalation"]["reason"]
    assert reason == "everything needed to fully resolve this"
    assert "unable to resolve at this tier" not in reason


@pytest.mark.asyncio
async def test_verdict_node_prompt_includes_calibration_fewshot(monkeypatch) -> None:
    """Regression test for a real bug found live: llama3.2:latest consistently
    judged can_resolve=False even for a genuinely complete Manager/RAG answer
    (reproduced 3/3 runs), apparently conflating "the customer must still act
    on this" with "I couldn't answer". VERDICT_FEWSHOT (backend/graph/tiers/
    base.py) was added to counter that bias — this asserts it's actually
    wired into the prompt the verdict model receives, not just defined."""
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.config.schema import Tier
    from backend.graph.handoff import initial_packet
    from backend.graph.tiers.base import VERDICT_FEWSHOT, TierVerdict, build_tier
    from tests.conftest import FakeLLM

    fake = FakeLLM()
    fake.script_text(AIMessage(content="Here is a complete, correct answer."))
    fake.script_structured(TierVerdict, TierVerdict(can_resolve=True))
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake)

    from backend.config.loader import get_config

    persona = get_config().personas.manager
    compiled = build_tier(Tier.MANAGER, persona, "llama3.2:latest", [], "no tools")

    state = {
        "messages": [HumanMessage(content="What does error E-317 mean?")],
        "packet": initial_packet("coc_verdict_fewshot_test"),
    }
    await compiled.ainvoke(state)

    assert fake.last_ainvoke_args is not None
    messages = fake.last_ainvoke_args[0]
    prompt_text = messages[0].content
    assert VERDICT_FEWSHOT in prompt_text


def test_make_model_leaves_empty_tool_list_unbound(monkeypatch) -> None:
    """`tools=[]` must return the model UNBOUND, never `.bind_tools([])` — some
    providers treat those differently, and the Front Desk guarantee rests on it."""
    from backend.graph.tiers import base as base_module

    calls: list[str] = []

    class _Model:
        def bind_tools(self, _tools):
            calls.append("bind_tools")
            return self

    monkeypatch.setattr("langchain_ollama.ChatOllama", lambda **_kw: _Model())

    result = base_module.make_model("llama3.2:latest", [])
    assert calls == []  # bind_tools was never called
    assert isinstance(result, _Model)


@pytest.mark.asyncio
async def test_tool_calls_in_one_turn_run_concurrently() -> None:
    """Multiple independent tool calls requested in a single turn must not be
    serialized. This isn't custom code — langgraph.prebuilt.ToolNode already
    fans them out via asyncio.gather — so this test is a regression guard on
    that behavior holding across langgraph upgrades, not on our own logic."""
    import time

    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, StateGraph
    from langgraph.prebuilt import ToolNode

    from backend.graph.state import CoCState

    @tool
    async def slow_a(x: str) -> str:
        """Artificially slow tool A."""
        import asyncio

        await asyncio.sleep(0.5)
        return f"a:{x}"

    @tool
    async def slow_b(x: str) -> str:
        """Artificially slow tool B."""
        import asyncio

        await asyncio.sleep(0.5)
        return f"b:{x}"

    graph = StateGraph(CoCState)
    graph.add_node("tools", ToolNode([slow_a, slow_b]))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    compiled = graph.compile()

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "slow_a", "args": {"x": "1"}, "id": "call_1"},
            {"name": "slow_b", "args": {"x": "2"}, "id": "call_2"},
        ],
    )
    start = time.monotonic()
    await compiled.ainvoke({"messages": [ai_msg]})
    elapsed = time.monotonic() - start

    # Sequential would be ~1.0s; concurrent is ~0.5s. 0.9s leaves generous
    # margin for scheduler jitter while still failing if this regresses to
    # sequential dispatch.
    assert elapsed < 0.9
