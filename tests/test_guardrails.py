"""Guardrail middleware tests.  (M5)

check_input/check_output are structured-output calls, exercised here with the
shared FakeLLM. guardrail_input_node's routing and state-update behavior
(abuse counting, PII redaction, off-scope decline) are tested directly against
backend/graph/supervisor.py.
"""

from __future__ import annotations

import pytest


def _verdict(**overrides):
    from backend.graph.middleware.guardrails import InputVerdict

    base = {
        "is_injection": False,
        "contains_pii": False,
        "is_abusive": False,
        "in_scope": True,
        "reason": "",
    }
    base.update(overrides)
    return InputVerdict(**base)


# ---------------------------------------------------------------------------
# check_input / check_output plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_input_uses_front_desk_model(
    monkeypatch: pytest.MonkeyPatch, fake_llm, config
) -> None:
    from langchain_core.messages import HumanMessage

    from backend.graph.middleware.guardrails import InputVerdict, check_input

    fake_llm.script_structured(InputVerdict, _verdict(is_abusive=True, reason="rude"))
    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)

    calls: list[str] = []
    monkeypatch.setattr(
        "backend.graph.tiers.base.make_model",
        lambda model_id, *a, **kw: (calls.append(model_id), fake_llm)[1],
    )

    state = {"messages": [HumanMessage(content="you are useless")]}
    verdict = await check_input(state)

    assert verdict.is_abusive is True
    assert calls == [config.models.front_desk]


@pytest.mark.asyncio
async def test_check_output_uses_ceo_model(
    monkeypatch: pytest.MonkeyPatch, fake_llm, config
) -> None:
    from backend.graph.middleware.guardrails import OutputVerdict, check_output

    fake_llm.script_structured(
        OutputVerdict,
        OutputVerdict(
            hallucinated_commitment=True,
            leaks_internals=False,
            unsafe_advice=False,
            reason="over-promised",
        ),
    )
    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)

    calls: list[str] = []
    monkeypatch.setattr(
        "backend.graph.tiers.base.make_model",
        lambda model_id, *a, **kw: (calls.append(model_id), fake_llm)[1],
    )

    verdict = await check_output({}, "I'll refund you right now, guaranteed.")

    assert verdict.passed is False
    assert calls == [config.models.ceo]


@pytest.mark.asyncio
async def test_check_output_tags_its_call_as_internal(
    monkeypatch: pytest.MonkeyPatch, fake_llm, config
) -> None:
    """Regression test for a real leak found live: check_output() runs INSIDE
    the CEO tier's "agent" graph node (called from ceo.py's response
    optimizer), sharing that node's langgraph_node metadata with the tier's
    real customer-facing response. Without the "coc_internal" tag,
    backend/api/main.py's token streamer can't tell them apart, and this
    call's raw structured-output JSON streams straight onto the customer's
    chat bubble — reproduced live as
    '...I'll do my best to assist you.{"hallucinated_commitment": false, ...}'
    glued onto a real CEO reply."""
    from backend.graph.middleware.guardrails import OutputVerdict, check_output

    fake_llm.script_structured(
        OutputVerdict,
        OutputVerdict(
            hallucinated_commitment=False, leaks_internals=False, unsafe_advice=False, reason=""
        ),
    )
    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)
    monkeypatch.setattr("backend.graph.tiers.base.make_model", lambda *a, **kw: fake_llm)

    await check_output({}, "A perfectly ordinary reply.")

    assert fake_llm.last_ainvoke_kwargs is not None
    assert "coc_internal" in fake_llm.last_ainvoke_kwargs.get("config", {}).get("tags", [])


def test_output_verdict_passed_requires_all_clear() -> None:
    from backend.graph.middleware.guardrails import OutputVerdict

    clean = OutputVerdict(
        hallucinated_commitment=False, leaks_internals=False, unsafe_advice=False, reason=""
    )
    assert clean.passed

    dirty = clean.model_copy(update={"leaks_internals": True})
    assert not dirty.passed


# ---------------------------------------------------------------------------
# guardrail_input_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardrail_noop_above_front_desk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only Front Desk gets screened — every other tier works from the packet,
    not raw input (see the module docstring in guardrails.py)."""
    from backend.config.schema import Tier
    from backend.graph.handoff import initial_packet
    from backend.graph.supervisor import guardrail_input_node

    def _boom(_state):
        msg = "check_input must not be called above Front Desk"
        raise AssertionError(msg)

    monkeypatch.setattr("backend.graph.middleware.guardrails.check_input", _boom)

    state = {"current_tier": Tier.MANAGER, "packet": initial_packet("x"), "messages": []}
    result = await guardrail_input_node(state)
    assert result == {"_guardrail_blocked": False}


@pytest.mark.asyncio
async def test_guardrail_passes_clean_message_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import HumanMessage

    from backend.config.schema import Tier
    from backend.graph.supervisor import guardrail_input_node

    async def _clean(_state):
        return _verdict()

    monkeypatch.setattr("backend.graph.middleware.guardrails.check_input", _clean)

    state = {
        "current_tier": Tier.FRONT_DESK,
        "messages": [HumanMessage(content="What are your store hours?")],
        "guardrail_hits": [],
    }
    result = await guardrail_input_node(state)
    assert result["_guardrail_blocked"] is False
    assert "messages" not in result


@pytest.mark.asyncio
async def test_guardrail_blocks_and_deescalates_on_abuse(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import HumanMessage

    from backend.config.schema import Tier
    from backend.graph.supervisor import guardrail_input_node, route_from_guardrail

    async def _abusive(_state):
        return _verdict(is_abusive=True, reason="insulting the agent")

    monkeypatch.setattr("backend.graph.middleware.guardrails.check_input", _abusive)

    state = {
        "current_tier": Tier.FRONT_DESK,
        "messages": [HumanMessage(content="you are a useless idiot")],
        "guardrail_hits": [],
        "abuse_count": 0,
    }
    result = await guardrail_input_node(state)

    assert result["_guardrail_blocked"] is True
    assert result["abuse_count"] == 1
    assert "guardrail_hits" in result and "abuse" in result["guardrail_hits"]
    assert route_from_guardrail(result) == "blocked"
    assert len(result["messages"]) == 1  # a de-escalating reply, not a hard refusal


@pytest.mark.asyncio
async def test_guardrail_closes_conversation_after_repeated_abuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.messages import HumanMessage

    from backend.config.schema import Tier
    from backend.graph.middleware.guardrails import MAX_ABUSE_WARNINGS
    from backend.graph.supervisor import guardrail_input_node

    async def _abusive(_state):
        return _verdict(is_abusive=True, reason="still abusive")

    monkeypatch.setattr("backend.graph.middleware.guardrails.check_input", _abusive)

    state = {
        "current_tier": Tier.FRONT_DESK,
        "messages": [HumanMessage(content="still being abusive")],
        "guardrail_hits": [],
        "abuse_count": MAX_ABUSE_WARNINGS - 1,
    }
    result = await guardrail_input_node(state)

    assert result["abuse_count"] == MAX_ABUSE_WARNINGS
    assert "pause here" in result["messages"][0].content.lower()


@pytest.mark.asyncio
async def test_guardrail_declines_off_scope_without_escalating(
    monkeypatch: pytest.MonkeyPatch, config
) -> None:
    """⚠ Off-scope must decline, never escalate — escalating an off-topic
    question just moves the problem up the ladder instead of resolving it."""
    from langchain_core.messages import HumanMessage

    from backend.config.schema import Tier
    from backend.graph.supervisor import guardrail_input_node

    async def _off_scope(_state):
        return _verdict(in_scope=False, reason="asking about the weather")

    monkeypatch.setattr("backend.graph.middleware.guardrails.check_input", _off_scope)
    monkeypatch.setattr("backend.config.loader.get_config", lambda: config)

    state = {
        "current_tier": Tier.FRONT_DESK,
        "messages": [HumanMessage(content="what's the weather like today?")],
        "guardrail_hits": [],
    }
    result = await guardrail_input_node(state)

    assert result["_guardrail_blocked"] is True
    assert "pending_escalation" not in result
    assert "off_scope" in result["guardrail_hits"]


@pytest.mark.asyncio
async def test_guardrail_redacts_pii_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import HumanMessage

    from backend.config.schema import Tier
    from backend.graph.supervisor import guardrail_input_node

    async def _has_pii(_state):
        return _verdict(contains_pii=True, reason="email present")

    monkeypatch.setattr("backend.graph.middleware.guardrails.check_input", _has_pii)

    original = HumanMessage(content="my email is jane@example.com, what's my order status?")
    state = {
        "current_tier": Tier.FRONT_DESK,
        "messages": [original],
        "guardrail_hits": [],
    }
    result = await guardrail_input_node(state)

    assert result["_guardrail_blocked"] is False  # PII is not a refusal
    redacted = result["messages"][0]
    assert redacted.id == original.id  # replaces the same message, doesn't append
    assert "jane@example.com" not in redacted.content
    assert "pii" in result["guardrail_hits"]


def test_route_from_guardrail() -> None:
    from backend.graph.supervisor import route_from_guardrail

    assert route_from_guardrail({"_guardrail_blocked": True}) == "blocked"
    assert route_from_guardrail({"_guardrail_blocked": False}) == "continue"
    assert route_from_guardrail({}) == "continue"
