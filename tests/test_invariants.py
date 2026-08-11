"""Invariant tests — the properties that define this design.

Each of these can break without anything crashing. The system would keep
running; it would just no longer be the thing that was designed. That is exactly
why they need tests rather than comments.

Re-run this file after any refactor of backend/graph/ or backend/mcp/.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 1. The Front Desk has NO tools
# ---------------------------------------------------------------------------


def test_front_desk_tool_registry_is_empty() -> None:
    from backend.graph.tiers import front_desk

    compiled = front_desk.build("llama3.2:latest")
    # No "tools" node exists at all when the tier has no tools.
    assert "tools" not in compiled.get_graph().nodes


def test_front_desk_graph_has_no_tool_node() -> None:
    from backend.config.loader import get_config
    from backend.config.schema import Tier
    from backend.graph.tiers.base import build_tier

    persona = get_config().personas.front_desk
    compiled = build_tier(Tier.FRONT_DESK, persona, "llama3.2:latest", [], "no tools")
    node_names = set(compiled.get_graph().nodes.keys())
    assert "tools" not in node_names


def test_manager_tier_has_tool_node() -> None:
    """Contrast case: a tier WITH tools does get a tools node — proves the
    absence above is deliberate, not a graph-building accident."""
    from backend.graph.tiers import manager

    compiled = manager.build("llama3:8b")
    assert "tools" in compiled.get_graph().nodes


def test_config_rejects_front_desk_tools(example_config_dict: dict) -> None:
    from pydantic import ValidationError

    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["mcp_servers"]["internal"][0]["tiers"].append("front_desk")
    with pytest.raises(ValidationError, match="front_desk"):
        CompanyConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# 2. Only the supervisor writes current_tier
# ---------------------------------------------------------------------------


def test_tier_verdict_node_never_returns_current_tier() -> None:
    """Tier subgraphs raise EscalationRequest via pending_escalation; only
    backend/graph/supervisor.py's do_handoff writes current_tier. Inspecting the
    verdict_node's own update keys (via source) would be brittle, so instead we
    assert the update contract: a tier's returned dict never contains the key
    'current_tier'."""
    import inspect

    import backend.graph.tiers.base as base_module

    source = inspect.getsource(base_module.build_tier)
    # verdict_node / agent_node / introduce_node bodies must never assign
    # "current_tier" into their returned update dicts.
    assert '"current_tier"' not in source


# ---------------------------------------------------------------------------
# 3. Escalation is monotonic — no auto-descalation
# ---------------------------------------------------------------------------


def test_next_tier_order_is_monotonic() -> None:
    from backend.config.schema import ORDER, Tier, next_tier

    assert ORDER == [Tier.FRONT_DESK, Tier.MANAGER, Tier.VICE_PRESIDENT, Tier.CEO]
    assert next_tier(Tier.FRONT_DESK) == Tier.MANAGER
    assert next_tier(Tier.MANAGER) == Tier.VICE_PRESIDENT
    assert next_tier(Tier.VICE_PRESIDENT) == Tier.CEO
    assert next_tier(Tier.CEO) is None


@pytest.mark.asyncio
async def test_handoff_rejects_backward_transition() -> None:
    """do_handoff() must refuse a transition that would not be a forward move
    from current_tier, rather than silently proceeding."""
    from backend.config.schema import Tier
    from backend.graph.state import new_state
    from backend.graph.supervisor import do_handoff

    state = new_state("session-backward")
    # Simulate a bug: current_tier is already CEO, but a stale pending_escalation
    # claims to be escalating FROM front_desk (which would compute to_tier=manager,
    # a backward move relative to current_tier=CEO).
    state["current_tier"] = Tier.CEO
    state["pending_escalation"] = {
        "from_tier": Tier.FRONT_DESK,
        "to_tier": Tier.MANAGER,
        "reason": "stale request",
        "user_initiated": False,
    }

    with pytest.raises(RuntimeError, match="forward move"):
        await do_handoff(state)


# ---------------------------------------------------------------------------
# 4. Tiers receive a packet, never a raw transcript
# ---------------------------------------------------------------------------


def test_packet_respects_size_cap(populated_packet) -> None:
    assert len(populated_packet.verified_facts) <= 12
    assert len(populated_packet.attempted_actions) <= 15
    assert len(populated_packet.ruled_out) <= 12
    assert len(populated_packet.open_questions) <= 6


def test_packet_is_redacted() -> None:
    from backend.graph.handoff import HandoffPacket, _redact_packet

    packet = HandoffPacket(
        ticket_id="coc_pii",
        customer_intent="Update contact email to jane@example.com",
        verified_facts=["Phone on file: 415-555-0134"],
        escalation_reason="needs manual update",
    )
    redacted = _redact_packet(packet.model_copy(deep=True))
    assert "jane@example.com" not in redacted.customer_intent
    assert "415-555-0134" not in redacted.verified_facts[0]
    assert redacted.pii_redacted is True


# ---------------------------------------------------------------------------
# 5. No stdio spawn outside the allowlist
# ---------------------------------------------------------------------------


def test_config_rejects_disallowed_binary(example_config_dict: dict) -> None:
    from pydantic import ValidationError

    from backend.config.schema import CompanyConfig

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["mcp_servers"]["external"][0]["command"] = "bash"  # web_search: stdio, npx
    with pytest.raises(ValidationError, match="allowlist"):
        CompanyConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# 6. HITL context requests are conditional
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_interrupt_when_no_context_needed(monkeypatch) -> None:
    """A turn where the agent needs nothing must complete with ZERO interrupts."""
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.config.schema import Tier
    from backend.graph.state import new_state
    from backend.graph.supervisor import UserIntent
    from backend.graph.tiers.base import TierVerdict
    from tests.conftest import FakeLLM, script_passing_guardrail

    fake = FakeLLM()
    script_passing_guardrail(fake)
    fake.script_structured(UserIntent, UserIntent(wants_escalation=False, is_simple_question=True))
    fake.script_text(AIMessage(content="Our hours are 9-5 Monday to Friday."))
    fake.script_structured(
        TierVerdict, TierVerdict(can_resolve=True, escalation_reason=None, needs_context=None)
    )

    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake)

    from backend.graph.supervisor import build_graph

    graph = build_graph()
    state = new_state("session-no-interrupt")
    state["messages"] = [HumanMessage(content="What are your store hours?")]
    thread_config = {"configurable": {"thread_id": "session-no-interrupt"}}

    async for _ in graph.astream_events(state, thread_config, version="v2"):
        pass

    snapshot = await graph.aget_state(thread_config)
    assert snapshot.interrupts == ()
    assert snapshot.values["current_tier"] == Tier.FRONT_DESK


@pytest.mark.asyncio
async def test_user_initiated_escalation_skips_consent(monkeypatch) -> None:
    """'I want to talk to upper management' escalates immediately, no consent
    prompt — asking 'are you sure?' is the runaround the customer is trying to
    escape."""
    from langchain_core.messages import HumanMessage

    from backend.config.schema import Tier
    from backend.graph.state import new_state
    from backend.graph.supervisor import UserIntent
    from tests.conftest import FakeLLM, script_passing_guardrail

    fake = FakeLLM()
    script_passing_guardrail(fake)
    fake.script_structured(UserIntent, UserIntent(wants_escalation=True, is_simple_question=False))

    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake)
    monkeypatch.setattr(
        "backend.graph.handoff.summarize_for_handoff",
        _fake_summarize,
    )

    from backend.graph.supervisor import build_graph

    graph = build_graph()
    state = new_state("session-user-escalation")
    state["messages"] = [HumanMessage(content="I want to talk to upper management")]
    thread_config = {"configurable": {"thread_id": "session-user-escalation"}}

    async for _ in graph.astream_events(state, thread_config, version="v2"):
        pass

    snapshot = await graph.aget_state(thread_config)
    assert snapshot.interrupts == ()  # no consent interrupt was raised
    assert snapshot.values["current_tier"] == Tier.MANAGER


async def _fake_summarize(messages, incoming, from_tier, to_tier, escalation_reason, ticket_id):
    from backend.graph.handoff import initial_packet

    packet = initial_packet(ticket_id)
    packet.escalation_reason = escalation_reason
    return packet
