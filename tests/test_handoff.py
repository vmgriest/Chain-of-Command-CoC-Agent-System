"""Handoff protocol tests.  (M1)

The behavioural claims here — facts accumulate, the packet stays bounded, PII
does not survive — are the ones worth guarding closely. The strongest ones live
in test_invariants.py; this file covers the details around them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.graph.handoff import (
    MAX_FACTS,
    HandoffPacket,
    initial_packet,
    redact,
)

# --- redaction --------------------------------------------------------------


def test_redact_email() -> None:
    text, hit = redact("Reach me at jane.doe@example.com please.")
    assert hit is True
    assert "[EMAIL]" in text
    assert "jane.doe@example.com" not in text


def test_redact_phone() -> None:
    text, hit = redact("Call me at 415-555-0134 tomorrow.")
    assert hit is True
    assert "[PHONE]" in text
    assert "415-555-0134" not in text


def test_redact_card() -> None:
    text, hit = redact("Card number is 4111 1111 1111 1111 for the refund.")
    assert hit is True
    assert "[CARD]" in text
    assert "4111 1111 1111 1111" not in text


def test_redact_returns_false_when_clean() -> None:
    text, hit = redact("What are your store hours?")
    assert hit is False
    assert text == "What are your store hours?"


def test_redact_does_not_mangle_order_ids() -> None:
    text, hit = redact("My order number is #48812, any update?")
    assert hit is False
    assert "#48812" in text


# --- packet construction -----------------------------------------------------


def test_initial_packet_is_empty() -> None:
    packet = initial_packet("coc_abc123")
    assert packet.verified_facts == []
    assert packet.attempted_actions == []
    assert packet.ruled_out == []
    assert packet.open_questions == []
    assert packet.escalation_reason == ""


def test_packet_enforces_max_length() -> None:
    with pytest.raises(ValidationError):
        HandoffPacket(
            ticket_id="coc_x",
            customer_intent="test",
            verified_facts=[f"fact {i}" for i in range(MAX_FACTS + 1)],
            escalation_reason="test",
        )


def test_estimated_tokens_is_reasonable(populated_packet: HandoffPacket) -> None:
    empty = initial_packet(populated_packet.ticket_id)
    assert populated_packet.estimated_tokens() > empty.estimated_tokens()
    assert populated_packet.estimated_tokens() > 0
    assert not populated_packet.is_over_budget()


# --- summarization ------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarizer_merges_incoming_packet(
    monkeypatch, populated_packet: HandoffPacket
) -> None:
    """Facts in the incoming packet appear in the outgoing one when the model
    faithfully carries them forward (scripted here) — this is the contract the
    summarizer prompt asks the model to uphold."""
    from backend.config.schema import Tier
    from backend.graph import handoff as handoff_module

    merged = populated_packet.model_copy(deep=True)
    merged.verified_facts = [*populated_packet.verified_facts, "New fact from this hop"]

    class _FakeStructured:
        async def ainvoke(self, *_a, **_kw):
            return merged

    class _FakeChatOllama:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr("langchain_ollama.ChatOllama", _FakeChatOllama)

    result = await handoff_module.summarize_for_handoff(
        messages=[],
        incoming=populated_packet,
        from_tier=Tier.FRONT_DESK,
        to_tier=Tier.MANAGER,
        escalation_reason="needs order lookup",
        ticket_id=populated_packet.ticket_id,
    )

    for fact in populated_packet.verified_facts:
        assert fact in result.verified_facts
    assert "New fact from this hop" in result.verified_facts


@pytest.mark.asyncio
async def test_over_budget_triggers_resummarization(
    monkeypatch, populated_packet: HandoffPacket
) -> None:
    from backend.config.schema import Tier
    from backend.graph import handoff as handoff_module

    oversized = populated_packet.model_copy(deep=True)
    oversized.verified_facts = [f"a very long fact entry number {i} " * 10 for i in range(10)]
    assert oversized.is_over_budget()

    trimmed = populated_packet.model_copy(deep=True)
    trimmed.verified_facts = ["concise fact"]
    assert not trimmed.is_over_budget()

    responses = [oversized, trimmed]

    class _FakeStructured:
        async def ainvoke(self, *_a, **_kw):
            return responses.pop(0)

    class _FakeChatOllama:
        def __init__(self, *_a, **_kw) -> None:
            pass

        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr("langchain_ollama.ChatOllama", _FakeChatOllama)

    result = await handoff_module.summarize_for_handoff(
        messages=[],
        incoming=None,
        from_tier=Tier.FRONT_DESK,
        to_tier=Tier.MANAGER,
        escalation_reason="needs order lookup",
        ticket_id="coc_budget",
    )

    assert not responses  # both scripted responses were consumed (one retry)
    assert not result.is_over_budget()


@pytest.mark.asyncio
async def test_summarizer_uses_destination_model(
    monkeypatch, populated_packet: HandoffPacket
) -> None:
    """The larger (destination) model summarizes, not the tier handing off."""
    from backend.config.loader import get_config
    from backend.config.schema import Tier
    from backend.graph import handoff as handoff_module

    seen_models: list[str] = []

    class _FakeStructured:
        async def ainvoke(self, *_a, **_kw):
            return populated_packet

    class _FakeChatOllama:
        def __init__(self, *, model: str, **_kw) -> None:
            seen_models.append(model)

        def with_structured_output(self, _schema):
            return _FakeStructured()

    monkeypatch.setattr("langchain_ollama.ChatOllama", _FakeChatOllama)

    await handoff_module.summarize_for_handoff(
        messages=[],
        incoming=None,
        from_tier=Tier.FRONT_DESK,
        to_tier=Tier.MANAGER,
        escalation_reason="needs order lookup",
        ticket_id="coc_model_choice",
    )

    config = get_config()
    assert seen_models == [config.models.manager]
