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

import os
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
# Start with these four patterns. TODO(M5): upgrade to a real PII detector;
#   regex will miss names, addresses, and anything non-US-shaped.
# Order matters: card (long digit runs) before phone (shorter digit runs) so a
# 16-digit card number isn't partially eaten by the phone pattern first.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),  # local@domain.tld
    # 13-19 total digits (grouped in runs of up to 4, with optional spaces/dashes
    # between groups), covers most real card lengths (Visa 16, Amex 15, etc.).
    # (?<!\d) / (?!\d) are "not preceded/followed by a digit" — without them this
    # would also match the middle of a longer, unrelated number.
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
    # Optional +1 country code, optional parens around the area code, then
    # XXX-XXX-XXXX with '-', '.', or a space as the separator.
    "phone": re.compile(r"(?<!\d)(?:\+?1[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)"),
    "ssn": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),  # XXX-XX-XXXX only (no bare-digit SSNs)
}


def redact(text: str) -> tuple[str, bool]:
    """Replace PII matches with typed placeholders (e.g. "[EMAIL]").

    Returns (redacted_text, was_anything_redacted).

    Placeholders must be typed, not blanked — a downstream tier needs to know an
    email was present in order to ask for it again.
    """
    redacted_any = False
    result = text
    for label, pattern in PII_PATTERNS.items():
        new_result, count = pattern.subn(f"[{label.upper()}]", result)
        if count:
            redacted_any = True
            result = new_result
    return result, redacted_any


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

    def estimated_tokens(self) -> int:
        """Rough token estimate (~4 chars/token). Not exact, but must track
        packet size monotonically as fields grow."""
        text = self.customer_intent + self.escalation_reason
        text += "".join(self.verified_facts)
        text += "".join(f"{a.tier}{a.action}{a.outcome}" for a in self.attempted_actions)
        text += "".join(self.ruled_out) + "".join(self.open_questions)
        return max(1, len(text) // 4)

    def is_over_budget(self) -> bool:
        return self.estimated_tokens() > MAX_PACKET_TOKENS


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

SUMMARIZER_PROMPT = """\
You are compiling a handoff packet as a customer support ticket moves from one \
support tier to the next. Merge the transcript below with the packet already \
carried forward — do NOT start fresh. Facts accumulate up the ladder; that \
accumulation is the entire point of this protocol.

Rules:
- Prefer specifics over hedges ("account #48812" beats "an account").
- Keep every fact and ruled-out item already present in the incoming packet \
unless the transcript below directly contradicts it.
- Record every failed attempt in ruled_out, with the reason it failed.
- Never invent facts that are not present in the transcript or the incoming packet.
- Keep every list within its size limit ({max_facts} facts, {max_actions} \
attempted actions, {max_ruled_out} ruled out, {max_open} open questions) — keep \
the most important entries if you must drop some.

Incoming packet (already established — carry all of it forward unless superseded):
{incoming}

Transcript since the incoming packet was created:
{transcript}

The tier handing off is: {from_tier}
The reason this tier could not resolve it: {escalation_reason}
"""


def _format_transcript(messages: list[BaseMessage]) -> str:
    lines = []
    for m in messages:
        role = getattr(m, "type", "message")
        content = getattr(m, "content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(no messages)"


def _redact_packet(packet: HandoffPacket) -> HandoffPacket:
    """Run redact() over every free-text field. Returns a new packet."""
    redacted_any = False

    def _r(text: str) -> str:
        nonlocal redacted_any
        new_text, hit = redact(text)
        redacted_any = redacted_any or hit
        return new_text

    packet.customer_intent = _r(packet.customer_intent)
    packet.escalation_reason = _r(packet.escalation_reason)
    packet.verified_facts = [_r(f) for f in packet.verified_facts]
    packet.ruled_out = [_r(f) for f in packet.ruled_out]
    packet.open_questions = [_r(f) for f in packet.open_questions]
    packet.attempted_actions = [
        AttemptedAction(tier=a.tier, action=_r(a.action), outcome=_r(a.outcome))
        for a in packet.attempted_actions
    ]
    packet.pii_redacted = redacted_any
    return packet


def _truncate_packet(packet: HandoffPacket) -> HandoffPacket:
    """Last resort when re-summarization is still over budget. Cuts to the caps
    rather than looping further."""
    packet.verified_facts = packet.verified_facts[:MAX_FACTS]
    packet.attempted_actions = packet.attempted_actions[:MAX_ACTIONS]
    packet.ruled_out = packet.ruled_out[:MAX_RULED_OUT]
    packet.open_questions = packet.open_questions[:MAX_OPEN_QUESTIONS]
    return packet


async def summarize_for_handoff(
    messages: list[BaseMessage],
    incoming: HandoffPacket | None,
    from_tier: Tier,
    to_tier: Tier,
    escalation_reason: str,
    ticket_id: str,
) -> HandoffPacket:
    """Produce the packet the next tier will receive.

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
    from langchain_ollama import ChatOllama

    from backend.config.loader import get_config

    config = get_config()
    model_id = config.models.get(to_tier)
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(model=model_id, base_url=base_url, temperature=0)
    structured_llm = llm.with_structured_output(HandoffPacket)

    incoming_json = (
        incoming.model_dump_json(indent=2) if incoming else "(none — this is the first hop)"
    )
    prompt = SUMMARIZER_PROMPT.format(
        max_facts=MAX_FACTS,
        max_actions=MAX_ACTIONS,
        max_ruled_out=MAX_RULED_OUT,
        max_open=MAX_OPEN_QUESTIONS,
        incoming=incoming_json,
        transcript=_format_transcript(messages),
        from_tier=from_tier.value,
        escalation_reason=escalation_reason,
    )

    raw_result = await structured_llm.ainvoke(prompt)
    result = (
        raw_result
        if isinstance(raw_result, HandoffPacket)
        else HandoffPacket.model_validate(raw_result)
    )
    result.ticket_id = ticket_id
    if not result.escalation_reason:
        result.escalation_reason = escalation_reason

    if result.is_over_budget():
        retry_prompt = prompt + (
            "\n\nThe previous attempt was too long. Be far more concise: merge "
            "similar facts into one entry each, and drop anything non-essential."
        )
        raw_retry = await structured_llm.ainvoke(retry_prompt)
        result = (
            raw_retry
            if isinstance(raw_retry, HandoffPacket)
            else HandoffPacket.model_validate(raw_retry)
        )
        result.ticket_id = ticket_id
        if not result.escalation_reason:
            result.escalation_reason = escalation_reason
        if result.is_over_budget():
            result = _truncate_packet(result)

    return _redact_packet(result)


def initial_packet(ticket_id: str) -> HandoffPacket:
    """Empty packet for a brand-new session at the Front Desk.

    Nothing has been tried yet, so every list is empty and escalation_reason is "".
    """
    return HandoffPacket(
        ticket_id=ticket_id,
        customer_intent="",
        escalation_reason="",
    )
