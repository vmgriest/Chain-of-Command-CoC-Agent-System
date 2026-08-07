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

    # --- CEO / human loop (M4) ---
    human_notified: bool  # session stays LIVE after this flips true


# TODO(M1): new_state(session_id) -> CoCState
#   Fresh session: front_desk, attempt_count 0, initial_packet(), no pendings.

# TODO(M1): reset_for_tier(state, tier) -> dict
#   Partial update applied on tier change: attempt_count -> 0,
#   tier_just_changed -> True, pending_escalation -> None.

# TODO(M1): INVARIANT TEST — current_tier must be monotonically non-decreasing
#   across a session. There is no auto-descalation: once at the CEO, a simple
#   follow-up question is answered by the CEO, not bounced back to the Front Desk.
