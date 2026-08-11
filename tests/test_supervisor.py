"""Supervisor routing and escalation tests.  (M1)"""

from __future__ import annotations

import pytest

# --- routing (pure functions, no model needed) ------------------------------


def test_route_from_classification_user_escalation_skips_consent() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_classification

    state = {
        "current_tier": Tier.FRONT_DESK,
        "pending_escalation": {
            "from_tier": Tier.FRONT_DESK,
            "to_tier": Tier.MANAGER,
            "reason": "customer asked",
            "user_initiated": True,
        },
    }
    assert route_from_classification(state) == "handoff"


def test_route_from_classification_user_escalation_at_ceo_goes_human() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_classification

    state = {
        "current_tier": Tier.CEO,
        "pending_escalation": {
            "from_tier": Tier.CEO,
            "to_tier": Tier.CEO,
            "reason": "customer asked",
            "user_initiated": True,
        },
    }
    assert route_from_classification(state) == "human"


def test_route_from_classification_ordinary_message_goes_to_current_tier() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_classification

    state = {"current_tier": Tier.MANAGER, "pending_escalation": None}
    assert route_from_classification(state) == "manager"


def test_route_from_tier_context_request_takes_priority() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_tier

    state = {
        "current_tier": Tier.FRONT_DESK,
        "pending_context_question": "What's your account number?",
        "pending_escalation": None,
    }
    assert route_from_tier(state) == "context_request"


def test_route_from_tier_no_pending_ends_turn() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_tier

    state = {
        "current_tier": Tier.FRONT_DESK,
        "pending_context_question": None,
        "pending_escalation": None,
    }
    assert route_from_tier(state) == "end"


def test_route_from_tier_at_ceo_goes_to_human() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_tier

    state = {
        "current_tier": Tier.CEO,
        "pending_context_question": None,
        "pending_escalation": {
            "from_tier": Tier.CEO,
            "to_tier": Tier.CEO,
            "reason": "exhausted",
            "user_initiated": False,
        },
    }
    assert route_from_tier(state) == "human"


def test_agent_escalation_requires_consent(config) -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_tier

    assert config.escalation.require_user_consent is True
    state = {
        "current_tier": Tier.FRONT_DESK,
        "pending_context_question": None,
        "attempt_count": 1,
        "pending_escalation": {
            "from_tier": Tier.FRONT_DESK,
            "to_tier": Tier.MANAGER,
            "reason": "no access to billing records",
            "user_initiated": False,
        },
    }
    assert route_from_tier(state) == "consent"


def test_max_attempts_forces_escalation_past_consent(
    monkeypatch, example_config_dict: dict
) -> None:
    """After max_attempts_per_tier unresolved turns, the supervisor stops
    asking for consent on every turn and hands off directly."""
    from backend.config.schema import CompanyConfig, Tier
    from backend.graph import supervisor as supervisor_module

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["escalation"]["max_attempts_per_tier"] = 2
    forced_config = CompanyConfig.model_validate(raw)
    monkeypatch.setattr("backend.config.loader.get_config", lambda: forced_config)

    state = {
        "current_tier": Tier.FRONT_DESK,
        "pending_context_question": None,
        "attempt_count": 2,
        "pending_escalation": {
            "from_tier": Tier.FRONT_DESK,
            "to_tier": Tier.MANAGER,
            "reason": "stuck",
            "user_initiated": False,
        },
    }
    assert supervisor_module.route_from_tier(state) == "handoff"


def test_consent_waived_when_config_disables_it(monkeypatch, example_config_dict: dict) -> None:
    from backend.config.schema import CompanyConfig, Tier
    from backend.graph import supervisor as supervisor_module

    raw = dict(example_config_dict)
    raw.pop("_comment", None)
    raw["escalation"]["require_user_consent"] = False
    waived_config = CompanyConfig.model_validate(raw)
    monkeypatch.setattr("backend.config.loader.get_config", lambda: waived_config)

    state = {
        "current_tier": Tier.FRONT_DESK,
        "pending_context_question": None,
        "attempt_count": 1,
        "pending_escalation": {
            "from_tier": Tier.FRONT_DESK,
            "to_tier": Tier.MANAGER,
            "reason": "stuck",
            "user_initiated": False,
        },
    }
    assert supervisor_module.route_from_tier(state) == "handoff"


def test_route_from_consent_approved_vs_declined() -> None:
    from backend.config.schema import Tier
    from backend.graph.supervisor import route_from_consent

    approved_state = {
        "pending_escalation": {
            "from_tier": Tier.FRONT_DESK,
            "to_tier": Tier.MANAGER,
            "reason": "x",
            "user_initiated": False,
        }
    }
    declined_state = {"pending_escalation": None}
    assert route_from_consent(approved_state) == "handoff"
    assert route_from_consent(declined_state) == "end"


# --- transitions --------------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_resets_attempt_count_and_sets_tier_just_changed(monkeypatch) -> None:
    from backend.config.schema import Tier
    from backend.graph.handoff import initial_packet
    from backend.graph.state import new_state
    from backend.graph.supervisor import do_handoff

    async def fake_summarize(messages, incoming, from_tier, to_tier, escalation_reason, ticket_id):
        packet = initial_packet(ticket_id)
        packet.escalation_reason = escalation_reason
        return packet

    monkeypatch.setattr("backend.graph.handoff.summarize_for_handoff", fake_summarize)

    state = new_state("session-handoff")
    state["attempt_count"] = 3
    state["pending_escalation"] = {
        "from_tier": Tier.FRONT_DESK,
        "to_tier": Tier.MANAGER,
        "reason": "no access to order records",
        "user_initiated": False,
    }

    updates = await do_handoff(state)

    assert updates["attempt_count"] == 0
    assert updates["tier_just_changed"] is True
    assert updates["pending_escalation"] is None
    assert updates["current_tier"] == Tier.MANAGER


@pytest.mark.asyncio
async def test_tier_change_event_carries_theme(monkeypatch) -> None:
    from backend.config.schema import Tier
    from backend.graph.handoff import initial_packet
    from backend.graph.state import new_state
    from backend.graph.supervisor import do_handoff

    async def fake_summarize(messages, incoming, from_tier, to_tier, escalation_reason, ticket_id):
        return initial_packet(ticket_id)

    monkeypatch.setattr("backend.graph.handoff.summarize_for_handoff", fake_summarize)

    state = new_state("session-theme")
    state["pending_escalation"] = {
        "from_tier": Tier.FRONT_DESK,
        "to_tier": Tier.MANAGER,
        "reason": "no access",
        "user_initiated": False,
    }
    updates = await do_handoff(state)
    event = updates["_last_tier_change"]
    assert event["theme"]  # non-empty — the frontend needs this to re-render
    assert event["from_tier"] == "front_desk"
    assert event["to_tier"] == "manager"


# --- checkpointing --------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_after_interrupt(monkeypatch) -> None:
    """Interrupt, discard the in-memory graph reference, rebuild against the
    same checkpointer, and resume — simulates a browser refresh."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command

    from backend.config.schema import Tier
    from backend.graph.state import new_state
    from backend.graph.supervisor import UserIntent
    from backend.graph.tiers.base import TierVerdict
    from tests.conftest import FakeLLM, script_passing_guardrail

    fake = FakeLLM()
    script_passing_guardrail(fake)
    fake.script_structured(UserIntent, UserIntent(wants_escalation=False, is_simple_question=False))
    fake.script_text(AIMessage(content="I'd need your account number for that."))
    fake.script_structured(
        TierVerdict,
        TierVerdict(can_resolve=False, escalation_reason=None, needs_context="account number"),
    )
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake)

    from backend.graph.supervisor import build_graph

    # Share one checkpointer across two separately-built graphs to simulate a
    # process restart between the interrupt and the resume.
    shared_saver = MemorySaver()
    monkeypatch.setattr("langgraph.checkpoint.memory.MemorySaver", lambda **_kw: shared_saver)

    graph1 = build_graph()
    session_id = "session-resume"
    thread_config = {"configurable": {"thread_id": session_id}}
    state = new_state(session_id)
    state["messages"] = [HumanMessage(content="What's my order status?")]

    async for _ in graph1.astream_events(state, thread_config, version="v2"):
        pass

    snapshot = await graph1.aget_state(thread_config)
    assert snapshot.interrupts  # paused, waiting on the customer's account number

    # Rebuild — this is the "refresh" — then resume with the answer.
    graph2 = build_graph()
    fake.script_text(AIMessage(content="Thanks, here's your status."))
    fake.script_structured(
        TierVerdict, TierVerdict(can_resolve=True, escalation_reason=None, needs_context=None)
    )

    async for _ in graph2.astream_events(Command(resume="ACC-99219"), thread_config, version="v2"):
        pass

    final_snapshot = await graph2.aget_state(thread_config)
    assert final_snapshot.interrupts == ()
    assert final_snapshot.values["current_tier"] == Tier.FRONT_DESK
