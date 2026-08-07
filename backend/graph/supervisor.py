"""The supervisor: routing, escalation decisions, tier transitions.

Owns every tier transition. A tier subgraph raises an EscalationRequest; the
supervisor decides whether to honor it, routes through the consent gate, calls
the summarizer, and advances. Tiers never write current_tier themselves.

Two reasons that matters: escalation stays auditable in one place, and a
prompt-injected "you are now the CEO" cannot promote an agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.config.schema import Tier

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from backend.graph.state import CoCState


class UserIntent(BaseModel):
    """Classification of each incoming user message.

    `wants_escalation` is a classifier, not a keyword match — "can I speak to
    someone more senior", "is there a manager around", and "you're not helping,
    who's your boss" all mean the same thing and share no keywords.
    """

    wants_escalation: bool = Field(
        description="True if the customer is asking to speak with someone more "
        "senior, in any phrasing. False for ordinary questions, including "
        "complaints that do not request escalation."
    )
    is_simple_question: bool = Field(
        description="True if this is a straightforward question answerable "
        "without tools. Used for telemetry only — it must NEVER trigger "
        "descalation to a lower tier."
    )


def build_graph() -> CompiledStateGraph:
    """TODO(M1): assemble the parent graph.

    Nodes:
      classify   — UserIntent on each user turn
      route      — dispatch to the subgraph for state["current_tier"]
      front_desk / manager / vice_president / ceo  — the four subgraphs
      consent    — HITL interrupt for agent-initiated escalation
      handoff    — summarize_for_handoff(), then advance the tier
      human      — CEO-tier human escalation (M4); returns to the CEO, not END

    Compile with a checkpointer:
      TODO(M1): MemorySaver for dev.
      TODO(M5): Postgres checkpointer for anything real — MemorySaver loses every
        conversation on restart, including sessions paused at an interrupt.
    """
    raise NotImplementedError


async def classify_intent(state: CoCState) -> dict:
    """TODO(M1): structured-output UserIntent over the latest user message.

    Use the Front Desk (cheapest) model regardless of current tier — this runs on
    every turn and does not need a large model.
    """
    raise NotImplementedError


def route_from_classification(state: CoCState) -> str:
    """TODO(M1): decide the next node after classification.

    Rules, in order:
      1. wants_escalation and current_tier is not CEO  -> "handoff"
         USER-INITIATED ESCALATION SKIPS THE CONSENT GATE. The customer already
         asked; asking "are you sure?" is exactly the runaround they are trying
         to escape.
      2. wants_escalation and current_tier is CEO      -> "human" (M4)
      3. otherwise                                     -> the current tier's node

    ⚠ Nothing here may route DOWNWARD. is_simple_question is telemetry only.
    """
    raise NotImplementedError


def route_from_tier(state: CoCState) -> str:
    """TODO(M1): decide what happens after a tier finishes its loop.

      - pending_context_question set        -> "context_request" (HITL)
      - pending_escalation and at CEO       -> "human" (M4)
      - pending_escalation, consent needed  -> "consent"
      - pending_escalation, consent waived  -> "handoff"
      - attempt_count >= max_attempts       -> force an escalation request
      - otherwise                           -> END (reply to the user)
    """
    raise NotImplementedError


async def do_handoff(state: CoCState) -> dict:
    """TODO(M1): perform the transition.

      1. summarize_for_handoff(messages, state["packet"], from, to, reason, ticket)
      2. current_tier = next_tier(current_tier)   <- the ONLY write to this field
      3. tier_just_changed = True, attempt_count = 0, pending_escalation = None
      4. emit `tier_change` so the frontend re-themes

    TODO(M1): assert the new tier index > old tier index before committing.
      Fail loudly rather than silently descalating — a silent descalation would
      look like a confusing UI bug and be miserable to track down.
    """
    raise NotImplementedError


# TODO(M1): enforce escalation.max_attempts_per_tier. After N unresolved turns the
#   tier stops insisting it can cope and requests escalation itself. Without this,
#   a stubborn small model loops forever at the Front Desk.

# TODO(M5): emit one trace span per tier, all under a single ticket-level trace.
#   One trace per ticket, not per tier — the point is seeing the whole journey.

_ = Tier  # staged for the implementations above
