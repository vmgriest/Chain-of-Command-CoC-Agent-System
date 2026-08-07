"""WebSocket wire protocol.

⚠ Mirrored in frontend/src/types/index.ts. Change both or neither.

Design note: tier transitions are EXPLICIT EVENTS, not something the client
infers from message content. The frontend re-themes on `tier_change`, and it
needs to know a transition happened and why — sniffing for "Hi, I'm Dwight" in
a token stream would be fragile and untestable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from backend.config.schema import Tier

# ---------------------------------------------------------------------------
# Server -> client
# ---------------------------------------------------------------------------


class TokenEvent(BaseModel):
    """One streamed token of an agent reply."""

    type: Literal["token"] = "token"
    content: str


class AgentIntroEvent(BaseModel):
    """A tier introducing itself after a handoff. Sent BEFORE its tokens so the
    UI can render the persona header first."""

    type: Literal["agent_intro"] = "agent_intro"
    tier: Tier
    persona_name: str
    persona_title: str


class TierChangeEvent(BaseModel):
    """Escalation happened. Drives the UI theme transition.

    `packet_summary` is a short human-readable line ("Carrying over: account
    #48812, Okta IdP, cert issues ruled out") shown in the transition divider —
    it makes the handoff protocol visible to the customer instead of implicit.
    """

    type: Literal["tier_change"] = "tier_change"
    from_tier: Tier
    to_tier: Tier
    from_persona: str
    to_persona: str
    theme: str
    reason: str
    packet_summary: str


class EscalationPromptEvent(BaseModel):
    """Agent-initiated escalation awaiting consent. The graph is paused at an
    interrupt until `escalation_response` arrives."""

    type: Literal["escalation_prompt"] = "escalation_prompt"
    from_tier: Tier
    to_tier: Tier
    to_persona: str
    to_title: str
    reason: str
    question: str


class ContextRequestEvent(BaseModel):
    """Agent needs a specific fact to continue. Paused at an interrupt.

    Only sent when TierVerdict.needs_context was non-null — most turns produce
    no event of this type at all.
    """

    type: Literal["context_request"] = "context_request"
    question: str
    persona_name: str


class HumanEscalationEvent(BaseModel):
    """CEO involved a human.

    ⚠ NOT a session terminator. The frontend renders a status banner and the
      customer keeps chatting with the CEO.
    """

    type: Literal["human_escalation"] = "human_escalation"
    channels: list[str]  # e.g. ["email", "push"]
    scheduling_link: str | None = None
    message: str
    session_continues: bool = True  # always True — kept explicit for the client


class ErrorEvent(BaseModel):
    """Something failed. `message` is customer-facing and must stay in persona —
    never a stack trace."""

    type: Literal["error"] = "error"
    message: str
    recoverable: bool = True


# ---------------------------------------------------------------------------
# Client -> server
# ---------------------------------------------------------------------------


class UserMessage(BaseModel):
    type: Literal["user_message"] = "user_message"
    content: str


class EscalationResponse(BaseModel):
    """Answer to EscalationPromptEvent. Resumes the interrupt."""

    type: Literal["escalation_response"] = "escalation_response"
    approved: bool


class ContextResponse(BaseModel):
    """Answer to ContextRequestEvent. Resumes the interrupt."""

    type: Literal["context_response"] = "context_response"
    answer: str


# TODO(M1): ServerEvent / ClientEvent discriminated unions on `type`.
# TODO(M1): parse_client_event(raw) -> ClientEvent, rejecting unknown types
#   with an ErrorEvent rather than a 500.
