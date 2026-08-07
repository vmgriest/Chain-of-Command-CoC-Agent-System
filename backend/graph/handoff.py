"""State Summarization & Handoff Protocol.  ⭐ WRITE THIS FIRST.

The problem this solves: passing raw message history up the chain accumulates
fluff. By the third hop the CEO is reading the Front Desk's small talk and
burning context on it.

The fix: each tier emits a typed, bounded HandoffPacket. Facts, not transcript.
The raw transcript stays available for audit and tracing — it just does not ride
along in the prompt.

Everything else in backend/graph/ is shaped by the schema below, which is why
this file comes first.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from backend.config.schema import Tier

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

# Hard caps. The packet is a summary; if it grows without limit it becomes the
# transcript again and the whole protocol is pointless.
MAX_FACTS = 12
MAX_ACTIONS = 15
MAX_RULED_OUT = 12
MAX_OPEN_QUESTIONS = 6
MAX_PACKET_TOKENS = 800


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# PII is stripped ONCE, at the tier boundary, on the way up — not at every tier.
# TODO(M1): start with these four patterns. TODO(M5): upgrade to a real PII
#   detector; regex will miss names, addresses, and anything non-US-shaped.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    # "email": re.compile(...),
    # "phone": re.compile(...),
    # "card":  re.compile(...),
    # "ssn":   re.compile(...),
}


def redact(text: str) -> tuple[str, bool]:
    """TODO(M1): replace PII matches with typed placeholders (e.g. "[EMAIL]").

    Returns (redacted_text, was_anything_redacted).

    Placeholders must be typed, not blanked — a downstream tier needs to know an
    email was present in order to ask for it again.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# The packet
# ---------------------------------------------------------------------------


class AttemptedAction(BaseModel):
    """One thing a tier tried, and how it went.

    Failures matter more than successes here — a recorded failure is what stops
    the next tier from trying the same thing.
    """

    tier: Tier
    action: str = Field(description="What was tried, e.g. 'rag_search(sso_troubleshooting)'")
    outcome: str = Field(description="What happened, e.g. 'docs cover Azure AD only'")


class HandoffPacket(BaseModel):
    """The contract between tiers. Tiers receive this — never a raw transcript.

    Populated by an LLM via structured output, so every field description below
    is doing double duty as prompt instruction. Word them carefully.
    """

    ticket_id: str

    customer_intent: str = Field(
        description="What the customer is actually trying to accomplish, in one sentence. "
        "The underlying goal, not the surface question."
    )

    verified_facts: list[str] = Field(
        default_factory=list,
        max_length=MAX_FACTS,
        description="Facts established and confirmed during the conversation. "
        "Only what is known — not what was guessed or assumed.",
    )

    attempted_actions: list[AttemptedAction] = Field(
        default_factory=list,
        max_length=MAX_ACTIONS,
        description="Everything tried so far, across all tiers, and its outcome.",
    )

    ruled_out: list[str] = Field(
        default_factory=list,
        max_length=MAX_RULED_OUT,
        description="Hypotheses positively eliminated. This is what stops the next "
        "tier re-litigating dead ends — be specific about what was ruled out and why.",
    )

    open_questions: list[str] = Field(
        default_factory=list,
        max_length=MAX_OPEN_QUESTIONS,
        description="What is still unknown and would unblock the problem if answered.",
    )

    sentiment: Literal["calm", "confused", "frustrated", "angry"] = "calm"

    escalation_reason: str = Field(
        description="Why this specific tier could not resolve it. Name the missing "
        "capability, not a vague 'needed more help'."
    )

    pii_redacted: bool = False

    # TODO(M1): estimated_tokens() -> int
    # TODO(M1): is_over_budget() -> bool  (compare against MAX_PACKET_TOKENS)


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

# TODO(M1): SUMMARIZER_PROMPT
#   Must instruct the model to:
#     - MERGE with the incoming packet, never start fresh. Facts accumulate up
#       the ladder; that accumulation is the entire point.
#     - Prefer specifics over hedges ("account #48812" beats "an account").
#     - Record failed attempts in ruled_out with the reason they failed.
#     - Never invent facts not present in the transcript.


async def summarize_for_handoff(
    messages: list[BaseMessage],
    incoming: HandoffPacket | None,
    from_tier: Tier,
    to_tier: Tier,
    escalation_reason: str,
    ticket_id: str,
) -> HandoffPacket:
    """TODO(M1): produce the packet the next tier will receive.

    Steps:
      1. Build the summarizer prompt from `messages` AND `incoming` — passing the
         incoming packet is what makes facts accumulate instead of reset.
      2. Call the model with .with_structured_output(HandoffPacket).
      3. Run redact() over every free-text field; set pii_redacted accordingly.
      4. If the result is over budget, re-summarize more aggressively (one retry,
         then truncate — do not loop).

    Which model summarizes? Use the DESTINATION tier's model: it is the larger of
    the two, and it is the one that has to act on the result.
    """
    raise NotImplementedError


def initial_packet(ticket_id: str) -> HandoffPacket:
    """TODO(M1): empty packet for a brand-new session at the Front Desk.

    Nothing has been tried yet, so every list is empty and escalation_reason is "".
    """
    raise NotImplementedError
