"""Shared graph state.

One state object flows through the supervisor and every tier subgraph. It is
checkpointed, which is what makes HITL interrupts survive a browser refresh.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from backend.config.schema import Tier
from backend.graph.handoff import HandoffPacket


class EscalationRequest(TypedDict):
    """A tier asking to be escalated FROM. Tiers cannot promote themselves — they
    raise this, and the supervisor decides whether to honor it."""

    from_tier: Tier
    to_tier: Tier
    reason: str
    user_initiated: bool  # skips the consent gate when True


class CoCState(TypedDict, total=False):
    """State for the whole conversation, not per-tier.

    Note `current_tier`: only backend/graph/supervisor.py writes it. Tier
    subgraphs read it. There is a test asserting this stays true.
    """

    # --- conversation ---
    # add_messages is a LangGraph reducer: a node returning {"messages": [...]}
    # APPENDS to this list (merging on message id if one repeats) instead of
    # overwriting it outright, the way a plain dict update would.
    messages: Annotated[list, add_messages]
    session_id: str
    ticket_id: str

    # --- tier position ---
    current_tier: Tier
    tier_just_changed: bool  # drives the "introduce yourself" behavior

    # --- handoff ---
    packet: HandoffPacket

    # --- escalation bookkeeping ---
    attempt_count: int  # resets on tier change
    pending_escalation: EscalationRequest | None

    # --- HITL ---
    pending_context_question: str | None
    context_request_count: int  # per-turn cap; reset when a new user message arrives
    escalation_declined: bool  # True right after a refusal; suppresses re-asking
    #   on the very next tier turn so a decline doesn't get immediately re-prompted

    # --- CEO / human loop (M4) ---
    human_notified: bool  # session stays LIVE after this flips true

    # --- guardrails (M5) ---
    abuse_count: int  # never resets across the session; repeated abuse escalates the response
    guardrail_hits: list[str]  # analytics: "injection" | "pii" | "abuse" | "off_scope", accumulates

    # --- analytics (M5) ---
    started_at: float  # time.time() at session start; duration = now - started_at
    turn_count: int  # incremented once per user message, in classify_intent
    user_initiated_escalations: int
    agent_initiated_escalations: int
    consent_refusals: int
    escalation_reasons: list[str]  # every reason a handoff cited, in order

    # --- transient, read once by the API layer to emit the matching WS event ---
    _last_tier_change: dict | None
    _last_human_escalation_channels: list[str] | None
    _guardrail_blocked: (
        bool  # set each turn by guardrail_input_node; read once by route_from_guardrail
    )


def new_state(session_id: str) -> CoCState:
    """Fresh session: front_desk, attempt_count 0, initial_packet(), no pendings."""
    import time
    import uuid

    from backend.graph.handoff import initial_packet

    ticket_id = f"coc_{uuid.uuid4().hex}"
    return CoCState(
        messages=[],
        session_id=session_id,
        ticket_id=ticket_id,
        current_tier=Tier.FRONT_DESK,
        tier_just_changed=True,
        packet=initial_packet(ticket_id),
        attempt_count=0,
        pending_escalation=None,
        pending_context_question=None,
        context_request_count=0,
        escalation_declined=False,
        human_notified=False,
        abuse_count=0,
        guardrail_hits=[],
        started_at=time.time(),
        turn_count=0,
        user_initiated_escalations=0,
        agent_initiated_escalations=0,
        consent_refusals=0,
        escalation_reasons=[],
    )


def reset_for_tier(state: CoCState, tier: Tier) -> dict:
    """Partial update applied on tier change: attempt_count -> 0,
    tier_just_changed -> True, pending_escalation -> None."""
    return {
        "current_tier": tier,
        "attempt_count": 0,
        "tier_just_changed": True,
        "pending_escalation": None,
    }


# INVARIANT — current_tier must be monotonically non-decreasing across a
#   session. There is no auto-descalation: once at the CEO, a simple follow-up
#   question is answered by the CEO, not bounced back to the Front Desk.
#   Enforced in backend/graph/supervisor.py::do_handoff; tested in
#   tests/test_invariants.py.
