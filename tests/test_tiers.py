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


def test_make_model_leaves_empty_tool_list_unbound(monkeypatch) -> None:
    """`tools=[]` must return the model UNBOUND, never `.bind_tools([])` — some
    providers treat those differently, and the Front Desk guarantee rests on it."""
    from backend.graph.tiers import base as base_module

    calls: list[str] = []

    class _Model:
        def bind_tools(self, _tools):
            calls.append("bind_tools")
            return self

    monkeypatch.setattr(
        "langchain_ollama.ChatOllama", lambda **_kw: _Model()
    )

    result = base_module.make_model("llama3.2:latest", [])
    assert calls == []  # bind_tools was never called
    assert isinstance(result, _Model)
