"""Human-in-the-loop middleware.

Two distinct interrupts, easy to conflate:

  1. ESCALATION CONSENT — the agent wants to hand off and asks permission first.
     Only for AGENT-initiated escalation. A customer who asked for a manager is
     never asked to confirm.

  2. CONTEXT REQUEST — the agent needs a fact from the customer (account number,
     order id) to continue.

⚠ The defining property of #2 is that it is CONDITIONAL. If the agent needs
  nothing, the loop runs start to finish with zero interrupts. This is a
  conditional interrupt, not a per-turn checkpoint — an "are you sure?" on every
  turn would make the whole system unusable.

Both resume cleanly from checkpoint, which is what lets a customer refresh the
browser mid-question and land back where they were.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.types import interrupt

if TYPE_CHECKING:
    from backend.config.schema import Tier
    from backend.graph.state import CoCState


async def request_escalation_consent(
    state: CoCState,
    from_tier: Tier,
    to_tier: Tier,
    reason: str,
) -> dict:
    """TODO(M1): pause and ask the customer whether to escalate.

    interrupt() payload -> the frontend's EscalationPrompt component:
        {"type": "escalation_prompt", "from_tier", "to_tier",
         "from_persona", "to_persona", "reason"}

    Phrase the question around the CAPABILITY GAP, not the agent's inadequacy:
      "I don't have access to your billing records from this desk. Would you like
       me to bring in a department manager who does?"

    On approval  -> set pending_escalation, route to handoff.
    On refusal   -> CLEAR pending_escalation and keep going at the current tier.
      Refusal must not leave the tier stuck re-asking every turn; note the
      refusal in state so the agent does not immediately propose it again.
    """
    raise NotImplementedError


async def request_context(state: CoCState, question: str) -> dict:
    """TODO(M1): pause and ask the customer for a specific piece of information.

    interrupt() payload -> the frontend's ContextRequest component:
        {"type": "context_request", "question", "persona"}

    Called ONLY when TierVerdict.needs_context is non-null. Never call
    unconditionally.

    TODO(M1): guard against loops — cap context requests per turn (2 is plenty).
      A model that keeps asking for one more detail will happily do so forever.
    """
    raise NotImplementedError


# TODO(M1): resume semantics.
#   LangGraph resumes an interrupted graph with Command(resume=value). The API
#   layer maps inbound `escalation_response` / `context_response` WS messages to
#   that. Verify the checkpointer restores state after a full process restart,
#   not just an in-memory resume — that is the case MemorySaver silently fails.

_ = interrupt  # staged for the implementations above
