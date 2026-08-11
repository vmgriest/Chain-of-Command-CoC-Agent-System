"""WebSocket wire protocol.

⚠ Mirrored in frontend/src/types/index.ts. Change both or neither.

Design note: tier transitions are EXPLICIT EVENTS, not something the client
infers from message content. The frontend re-themes on `tier_change`, and it
needs to know a transition happened and why — sniffing for "Hi, I'm Dwight" in
a token stream would be fragile and untestable.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

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
    channels: list[str]  # e.g. ["email", "scheduling"]
    scheduling_link: str | None = None
    message: str
    session_continues: bool = True  # always True — kept explicit for the client


class ErrorEvent(BaseModel):
    """Something failed. `message` is customer-facing and must stay in persona —
    never a stack trace."""

    type: Literal["error"] = "error"
    message: str
    recoverable: bool = True


class TurnEndEvent(BaseModel):
    """The current turn's streaming is done — whether it ended normally or
    paused at an interrupt. The client stops treating the in-progress message
    bubble as streaming. Explicit rather than inferred: the client cannot tell
    "no more tokens yet" from "no more tokens ever" without this."""

    type: Literal["turn_end"] = "turn_end"


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


ServerEvent = (
    TokenEvent
    | AgentIntroEvent
    | TierChangeEvent
    | EscalationPromptEvent
    | ContextRequestEvent
    | HumanEscalationEvent
    | ErrorEvent
    | TurnEndEvent
)

ClientEvent = Annotated[
    UserMessage | EscalationResponse | ContextResponse,
    Field(discriminator="type"),
]

_client_event_adapter: TypeAdapter[ClientEvent] = TypeAdapter(ClientEvent)


def parse_client_event(raw: dict) -> ClientEvent | None:
    """Parse an inbound WS message into a typed ClientEvent.

    Returns None for anything that doesn't validate — the caller sends an
    ErrorEvent back over the wire rather than letting a bad payload 500 the
    connection.
    """
    try:
        return _client_event_adapter.validate_python(raw)
    except Exception:  # noqa: BLE001 - any malformed payload maps to None
        return None
