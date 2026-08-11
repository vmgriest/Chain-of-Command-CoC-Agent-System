"""backend/api/main.py — WebSocket session-start behavior.

_greet_new_session() doesn't invoke any model itself (introduce() is pure
Python), but build_graph() constructs a ChatOllama client per tier as a side
effect of compiling, so make_model is still faked here for consistency with
the rest of the suite and to guarantee no accidental network call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def fake_websocket():
    ws = AsyncMock()
    sent: list[dict] = []

    async def _capture(payload):
        sent.append(payload)

    ws.send_json.side_effect = _capture
    ws.sent = sent
    return ws


@pytest.mark.asyncio
async def test_greet_new_session_sends_intro_before_any_user_message(
    monkeypatch: pytest.MonkeyPatch, fake_llm, fake_websocket
) -> None:
    """Front Desk must greet the customer proactively on connect, the same
    way a post-handoff tier introduces itself immediately — no user message
    required first."""
    from backend.api.main import _greet_new_session
    from backend.config.schema import Tier
    from backend.graph.supervisor import build_graph

    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": "greet-test"}}

    await _greet_new_session(fake_websocket, graph, thread_config)

    assert fake_websocket.sent[0]["type"] == "agent_intro"
    assert fake_websocket.sent[0]["tier"] == Tier.FRONT_DESK
    assert fake_websocket.sent[0]["persona_name"] == "Penny"
    assert fake_websocket.sent[1]["type"] == "token"
    assert "Penny" in fake_websocket.sent[1]["content"]
    assert fake_websocket.sent[-1]["type"] == "turn_end"


@pytest.mark.asyncio
async def test_greet_new_session_commits_state_so_intro_never_repeats(
    monkeypatch: pytest.MonkeyPatch, fake_llm, fake_websocket
) -> None:
    """After the proactive greeting, the customer's actual first message must
    NOT trigger a second self-introduction — tier_just_changed must already
    be False, and the greeting message must already be in state."""
    from backend.api.main import _greet_new_session
    from backend.graph.supervisor import build_graph

    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": "greet-test-2"}}

    await _greet_new_session(fake_websocket, graph, thread_config)

    snapshot = await graph.aget_state(thread_config)
    assert snapshot.values["tier_just_changed"] is False
    contents = [getattr(m, "content", None) for m in snapshot.values["messages"]]
    assert any("Penny" in (c or "") for c in contents)


@pytest.mark.asyncio
async def test_greet_new_session_seeds_valid_ticket_and_session_ids(
    monkeypatch: pytest.MonkeyPatch, fake_llm, fake_websocket
) -> None:
    from backend.api.main import _greet_new_session
    from backend.graph.supervisor import build_graph

    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": "greet-test-3"}}

    await _greet_new_session(fake_websocket, graph, thread_config)

    snapshot = await graph.aget_state(thread_config)
    assert snapshot.values["session_id"] == "greet-test-3"
    assert snapshot.values["ticket_id"].startswith("coc_")


@pytest.mark.asyncio
async def test_stream_turn_does_not_resend_agent_intro_on_an_ordinary_turn(
    monkeypatch: pytest.MonkeyPatch, fake_llm, fake_websocket
) -> None:
    """Regression test for a real bug found live: "introduce" is every tier
    subgraph's ENTRY POINT, so its on_chain_end boundary fires on every single
    turn — not just a fresh handoff. introduce_node itself only returns a
    message when tier_just_changed is True, but _stream_turn used to send
    AgentIntroEvent unconditionally off that boundary regardless. The
    frontend's agent_intro handler opens a brand new chat bubble
    (startAgentMessage()) — on top of the one MessageInput.tsx already opens
    optimistically on send — so every ordinary follow-up turn left a stray,
    permanently-empty "streaming" bubble in the UI. Only the very first
    intro (via _greet_new_session) should ever emit agent_intro; a normal
    follow-up message in the same tier must not repeat it."""
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.api.main import _greet_new_session, _stream_turn
    from backend.graph.middleware.guardrails import InputVerdict
    from backend.graph.supervisor import UserIntent, build_graph
    from backend.graph.tiers.base import TierVerdict

    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)
    graph = build_graph()
    thread_config = {"configurable": {"thread_id": "no-repeat-intro-test"}}

    await _greet_new_session(fake_websocket, graph, thread_config)
    assert sum(1 for e in fake_websocket.sent if e["type"] == "agent_intro") == 1
    fake_websocket.sent.clear()

    fake_llm.script_structured(
        InputVerdict,
        InputVerdict(
            is_injection=False, contains_pii=False, is_abusive=False, in_scope=True, reason=""
        ),
    )
    fake_llm.script_structured(
        UserIntent, UserIntent(wants_escalation=False, is_simple_question=False)
    )
    fake_llm.script_text(AIMessage(content="Sure, here's the answer to your follow-up."))
    fake_llm.script_structured(TierVerdict, TierVerdict(can_resolve=True))

    await _stream_turn(
        fake_websocket,
        graph,
        thread_config,
        {"messages": [HumanMessage(content="a normal follow-up question")]},
    )

    assert sum(1 for e in fake_websocket.sent if e["type"] == "agent_intro") == 0
