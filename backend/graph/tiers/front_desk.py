"""Tier 1 — Front Desk.  NO TOOLS.

Answers only from what the base model was trained on. If the question is about
something that shipped after the cutoff, it cannot help — it says so and offers
to escalate. That limitation is the design, not a bug: it is what makes tier 1
cheap and fast enough to absorb the bulk of traffic.

Capabilities: input guardrails, fast triage, handoffs, prompt chaining.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.config.loader import get_config
from backend.config.schema import Tier
from backend.graph.tiers.base import build_tier

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

CAPABILITY_DESCRIPTION = """\
You have no tools. You can only answer from your own training. You cannot look
anything up, search the web, read company documents, or access customer records.
When a question needs any of those, say so plainly and offer to bring in a manager.
"""


def build(model_id: str) -> CompiledStateGraph:
    """build_tier(Tier.FRONT_DESK, persona, model_id, tools=[], ...).

    ⚠ `tools` is [] and must stay []. See the invariant note in tiers/base.py.
    """
    persona = get_config().personas.front_desk
    return build_tier(Tier.FRONT_DESK, persona, model_id, [], CAPABILITY_DESCRIPTION)


# TODO(M1+): triage(state) -> intent classification.
#   Structured output over the user's message: in_scope, wants_escalation,
#   estimated_complexity. Runs BEFORE the main agent call so an obviously
#   out-of-scope or escalation-seeking message never burns a full generation.
#   Note: user-initiated escalation is already handled by the supervisor's
#   classify_intent() on every turn; this would be a Front-Desk-local speedup.

# TODO(M5): input guardrails run here and nowhere else — this is the only tier
#   that touches unfiltered user input. Prompt injection, PII, abuse, and scope
#   checks against company.support_scope.

_ = Tier  # staged for the implementation above
