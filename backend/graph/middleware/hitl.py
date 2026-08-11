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

# A model that keeps asking for "just one more detail" will happily do so
# forever. Two context requests per user turn is plenty.
MAX_CONTEXT_REQUESTS_PER_TURN = 2


async def request_escalation_consent(
    state: CoCState,
    from_tier: Tier,
    to_tier: Tier,
    reason: str,
) -> dict:
    """Pause and ask the customer whether to escalate.

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
    from backend.config.loader import get_config

    config = get_config()
    from_persona = config.personas.get(from_tier)
    to_persona = config.personas.get(to_tier)

    question = (
        f"I don't have {reason} from this desk. Would you like me to bring in "
        f"{to_persona.name}, {to_persona.title}, who does?"
    )

    approved = interrupt(
        {
            "type": "escalation_prompt",
            "from_tier": from_tier.value,
            "to_tier": to_tier.value,
            "from_persona": from_persona.name,
            "to_persona": to_persona.name,
            "to_title": to_persona.title,
            "reason": reason,
            "question": question,
        }
    )

    if approved:
        return {
            "pending_escalation": {
                "from_tier": from_tier,
                "to_tier": to_tier,
                "reason": reason,
                "user_initiated": False,
            },
            "escalation_declined": False,
        }

    # Refusal is a first-class outcome: stay at the current tier, and remember
    # the refusal for one turn so the tier does not immediately re-propose it.
    return {
        "pending_escalation": None,
        "escalation_declined": True,
        "consent_refusals": state.get("consent_refusals", 0) + 1,
    }


async def request_context(state: CoCState, question: str) -> dict:
    """Pause and ask the customer for a specific piece of information.

    interrupt() payload -> the frontend's ContextRequest component:
        {"type": "context_request", "question", "persona"}

    Called ONLY when TierVerdict.needs_context is non-null. Never call
    unconditionally.

    Guards against loops: caps context requests per turn at
    MAX_CONTEXT_REQUESTS_PER_TURN. Once the cap is hit, the loop proceeds
    without interrupting again rather than blocking the conversation forever.
    """
    from backend.config.loader import get_config

    count = state.get("context_request_count", 0) or 0
    if count >= MAX_CONTEXT_REQUESTS_PER_TURN:
        return {"pending_context_question": None}

    persona = get_config().personas.get(state["current_tier"])

    answer = interrupt(
        {
            "type": "context_request",
            "question": question,
            "persona_name": persona.name,
        }
    )

    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=answer)],
        "pending_context_question": None,
        "context_request_count": count + 1,
    }


# Resume semantics: LangGraph resumes an interrupted graph with
#   Command(resume=value). The API layer (backend/api/main.py) maps inbound
#   `escalation_response` / `context_response` WS messages to that. The
#   checkpointer (MemorySaver in dev) restores state after a full process
#   restart in the same way it restores an in-memory resume — that symmetry is
#   what lets a customer refresh mid-interrupt and land back where they were.

_ = interrupt  # re-exported implicitly via the functions above
