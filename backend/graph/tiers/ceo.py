"""Tier 4 — CEO.  ALL TOOLS + HUMAN ESCALATION.

The last stop. Re-attempts the problem from scratch with the full toolset before
reaching for a person.

Capabilities: evaluator-optimizer, human-in-the-loop, observability, output guardrails.

Two behaviors that are easy to get wrong:

  1. THE SESSION DOES NOT END. When the CEO emails an admin or books a call, the
     chat stays live. The customer is told what happened and what to expect, and
     can keep talking.

  2. NO AUTO-DESCALATION. A simple follow-up at this tier ("what's your refund
     window?") is just answered here. The customer is never bounced back down.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.config.loader import get_config
from backend.config.schema import Tier
from backend.graph.tiers.base import build_tier

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

CAPABILITY_DESCRIPTION = """\
You have every tool available in this organization. You are the final escalation
point, so exhaust your own options before involving a human. If you do involve
one, tell the customer exactly what you did and what happens next — and keep
helping them in the meantime.
"""

# --- evaluator-optimizer ---------------------------------------------------

MAX_OPTIMIZE_ITERATIONS = 3
MAX_OPTIMIZE_TOKENS = 8000


class DraftEvaluation(BaseModel):
    """TODO(M4): explicit pass/fail criteria, not a vibe check.

    The evaluator is a SEPARATE model call from the drafter. Asking one call to
    both write and grade its own answer produces agreeable nonsense.
    """

    addresses_intent: bool = Field(description="Does this answer what the customer actually wants?")
    factually_grounded: bool = Field(description="Is every claim backed by a tool result or document?")
    no_unbacked_promises: bool = Field(description="Does it avoid committing the company to anything unverified?")
    actionable: bool = Field(description="Can the customer act on this, or is it vague?")
    critique: str = Field(description="What specifically to fix. Empty when all checks pass.")

    # TODO(M4): passed property -> all four bools True


def build(model_id: str) -> CompiledStateGraph:
    """build_tier(Tier.CEO, ..., tools=stub_tools(), ...)
    TODO(M4): wrap the agent node in the evaluator-optimizer loop below."""
    persona = get_config().personas.ceo
    return build_tier(Tier.CEO, persona, model_id, stub_tools(), CAPABILITY_DESCRIPTION)


def stub_tools() -> list[BaseTool]:
    """VP stubs plus a stub notify_human()."""
    from langchain_core.tools import tool

    from backend.graph.tiers.vice_president import stub_tools as vp_stub_tools

    @tool
    def notify_human(reason: str) -> str:
        """Loop in a human admin when every automated option is exhausted."""
        return (
            f"STUB: would notify the human admin now (reason: {reason!r}). "
            f"(Real email/push/scheduling notifications land in M4.)"
        )

    return [*vp_stub_tools(), notify_human]


# TODO(M4): optimize_loop(state) -> str
#   draft -> evaluate -> revise, bounded by MAX_OPTIMIZE_ITERATIONS *and*
#   MAX_OPTIMIZE_TOKENS. Return the best draft on exhaustion, never an error —
#   the customer gets an imperfect answer rather than a failure.
#   Emit each iteration to the trace so the loop is inspectable (M5).

# TODO(M4): escalate_to_human(reason, urgency) tool
#   Fans out to backend/notifications/: email, push, scheduling link.
#   Attaches the HandoffPacket so the admin has full context without reading
#   the transcript — same protocol, different consumer.
#   Sets state["human_notified"] = True, emits the `human_escalation` event,
#   and RETURNS TO THE CONVERSATION. Must not end the session.

# TODO(M5): output guardrails apply here and nowhere else — this is the last tier
#   before the customer. Check for hallucinated commitments, leaked internals,
#   and unsafe advice.

_ = Tier  # staged for the implementation above
