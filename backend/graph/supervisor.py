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

from backend.config.schema import ORDER, Tier, next_tier
from backend.graph.state import CoCState  # noqa: TC001 - needed at runtime; see

# the identical note in backend/graph/tiers/base.py.

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


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


def _last_user_text(messages: list) -> str:
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _summarize_packet_for_ui(packet) -> str:  # noqa: ANN001
    """Short human-readable line for the tier_change transition divider, e.g.
    'Carrying over: account #48812, Okta IdP, cert issues ruled out'."""
    bits = [*packet.verified_facts[:2], *packet.ruled_out[:1]]
    if not bits:
        return "Carrying over: your conversation so far."
    return "Carrying over: " + "; ".join(bits)


CLASSIFY_FEWSHOT = """\
Examples:
- "I want to talk to upper management right now." -> wants_escalation=true
- "can I speak to someone more senior" -> wants_escalation=true
- "is there a manager around" -> wants_escalation=true
- "you're not helping, who's your boss" -> wants_escalation=true
- "this is really frustrating" -> wants_escalation=false (venting, not asking for anyone)
- "what are your store hours?" -> wants_escalation=false (ordinary question)
- "my order never arrived and I am furious" -> wants_escalation=false (complaint,
  no request for escalation)
"""


async def classify_intent(state: CoCState) -> dict:
    """Structured-output UserIntent over the latest user message.

    Use the Front Desk (cheapest) model regardless of current tier — this runs on
    every turn and does not need a large model. Small models need the few-shot
    examples below to reliably separate "asking for someone senior" from
    ordinary frustration — tested against the exact phrasings this classifier
    must distinguish (see tests/test_supervisor.py).
    """
    from backend.config.loader import get_config
    from backend.graph.tiers.base import make_model

    config = get_config()
    model = make_model(config.models.front_desk, [], temperature=0)
    model = model.with_structured_output(UserIntent)
    text = _last_user_text(state["messages"])
    prompt = (
        "You are a classifier for a customer support chat. Decide if the "
        "customer is explicitly asking to be escalated to a more senior person "
        "(a manager, supervisor, someone in charge), in any phrasing — including "
        "indirect requests like asking who is in charge or if a manager is "
        "available. Frustration or a hard question, without an actual request "
        "for someone senior, is wants_escalation=false.\n\n"
        f"{CLASSIFY_FEWSHOT}\n"
        f"Customer message: {text!r}\n"
    )
    intent: UserIntent = await model.ainvoke(prompt)

    updates: dict = {
        # per-turn HITL bookkeeping resets with every new user message
        "context_request_count": 0,
        "turn_count": state.get("turn_count", 0) + 1,
    }

    if intent.wants_escalation:
        current_tier = state["current_tier"]
        target = next_tier(current_tier)
        updates["pending_escalation"] = {
            "from_tier": current_tier,
            "to_tier": target if target is not None else current_tier,
            "reason": "the customer asked to speak with someone more senior",
            "user_initiated": True,
        }
    else:
        updates["pending_escalation"] = None

    return updates


def route_from_classification(state: CoCState) -> str:
    """Decide the next node after classification.

    Rules, in order:
      1. wants_escalation and current_tier is not CEO  -> "handoff"
         USER-INITIATED ESCALATION SKIPS THE CONSENT GATE. The customer already
         asked; asking "are you sure?" is exactly the runaround they are trying
         to escape.
      2. wants_escalation and current_tier is CEO      -> "human"
      3. otherwise                                     -> the current tier's node

    ⚠ Nothing here may route DOWNWARD. is_simple_question is telemetry only.
    """
    pending = state.get("pending_escalation")
    if pending is not None and pending.get("user_initiated"):
        if state["current_tier"] == Tier.CEO:
            return "human"
        return "handoff"
    return state["current_tier"].value


def route_from_tier(state: CoCState) -> str:
    """Decide what happens after a tier finishes its loop.

    - pending_context_question set        -> "context_request" (HITL)
    - pending_escalation and at CEO       -> "human"
    - pending_escalation, consent needed  -> "consent"
    - pending_escalation, consent waived  -> "handoff"
    - attempt_count >= max_attempts       -> force straight to handoff/human,
      skipping consent — repeatedly asking "are you sure?" IS the failure mode
      max_attempts exists to stop.
    - otherwise                           -> END (reply to the user)
    """
    from backend.config.loader import get_config

    if state.get("pending_context_question"):
        return "context_request"

    pending = state.get("pending_escalation")
    if pending is None:
        return "end"

    if state["current_tier"] == Tier.CEO:
        return "human"

    config = get_config()
    attempt_count = state.get("attempt_count", 0)
    forced = attempt_count >= config.escalation.max_attempts_per_tier
    consent_needed = config.escalation.require_user_consent and not forced

    return "consent" if consent_needed else "handoff"


def route_from_consent(state: CoCState) -> str:
    """After the consent interrupt resumes: approved -> handoff, declined -> end."""
    return "handoff" if state.get("pending_escalation") else "end"


def route_after_context(state: CoCState) -> str:
    """After a context-request interrupt resumes, hand control back to whichever
    tier is currently active so it can continue reasoning with the new answer."""
    return state["current_tier"].value


async def consent_node(state: CoCState) -> dict:
    from backend.graph.middleware.hitl import request_escalation_consent

    pending = state["pending_escalation"]
    return await request_escalation_consent(
        state, pending["from_tier"], pending["to_tier"], pending["reason"]
    )


async def context_request_node(state: CoCState) -> dict:
    from backend.graph.middleware.hitl import request_context

    question = state["pending_context_question"]
    return await request_context(state, question)


async def guardrail_input_node(state: CoCState) -> dict:
    """Screen the latest customer message — Front Desk only (see the module
    docstring in backend/graph/middleware/guardrails.py for why). A no-op at
    every other tier: everything above Front Desk works from a HandoffPacket,
    not raw customer input, at the moment a handoff happens, but the customer
    keeps typing directly to whichever tier is current after that — this node
    still runs every turn, it just only takes action when current_tier is
    FRONT_DESK.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.config.loader import get_config
    from backend.graph.handoff import redact
    from backend.graph.middleware.guardrails import (
        MAX_ABUSE_WARNINGS,
        check_input,
        last_human_message,
    )

    if state["current_tier"] != Tier.FRONT_DESK:
        return {"_guardrail_blocked": False}

    verdict = await check_input(state)
    hits = [
        *state.get("guardrail_hits", []),
        *(["injection"] if verdict.is_injection else []),
        *(["pii"] if verdict.contains_pii else []),
        *(["abuse"] if verdict.is_abusive else []),
        *(["off_scope"] if not verdict.in_scope else []),
    ]
    updates: dict = {"guardrail_hits": hits} if hits != state.get("guardrail_hits", []) else {}

    if verdict.contains_pii:
        last_human = last_human_message(state["messages"])
        if last_human is not None:
            redacted_text, was_redacted = redact(str(last_human.content))
            if was_redacted:
                updates["messages"] = [HumanMessage(content=redacted_text, id=last_human.id)]

    if verdict.is_abusive:
        abuse_count = state.get("abuse_count", 0) + 1
        updates["abuse_count"] = abuse_count
        text = (
            "I need to pause here — repeated abusive language means I can't keep "
            "this conversation going right now. Please reach back out when we can "
            "keep this respectful."
            if abuse_count >= MAX_ABUSE_WARNINGS
            else "I'm glad to help, but I'll need us to keep this respectful. "
            "What can I help you with?"
        )
        updates["messages"] = [*updates.get("messages", []), AIMessage(content=text)]
        updates["_guardrail_blocked"] = True
        return updates

    if not verdict.in_scope:
        support_scope = ", ".join(get_config().company.support_scope) or "general support"
        text = (
            f"That's outside what I can help with here — we handle {support_scope}. "
            f"Is there something in that area I can help with?"
        )
        updates["messages"] = [*updates.get("messages", []), AIMessage(content=text)]
        updates["_guardrail_blocked"] = True
        return updates

    updates["_guardrail_blocked"] = False
    return updates


def route_from_guardrail(state: CoCState) -> str:
    return "blocked" if state.get("_guardrail_blocked") else "continue"


async def human_escalation_node(state: CoCState) -> dict:
    """CEO's own TierVerdict gave up (can_resolve=False, already at CEO).
    Fans out to real notification channels (backend/notifications/) and keeps
    the session live — a human hop never ends the conversation.

    This is the AUTOMATIC path. The CEO can also escalate PROACTIVELY mid-turn
    via its own `escalate_to_human` tool (backend/graph/tiers/ceo.py), which
    updates the same `human_notified` / `_last_human_escalation_channels`
    state fields via a returned Command — backend/api/main.py detects either
    path identically, by diffing `human_notified` across the turn, not by node
    name.
    """
    from langchain_core.messages import AIMessage

    from backend.notifications import notify_human, session_url

    packet = state["packet"]
    reason = packet.escalation_reason or "unable to resolve at any tier"
    url = session_url(state["session_id"])
    channels = await notify_human(packet, reason, urgency="normal", session_url_=url)

    text = (
        "I've exhausted what I can do from here, so I've flagged this for a "
        "member of our team to follow up personally. In the meantime, I'm still "
        "right here if there's anything else I can help with."
    )
    return {
        "messages": [AIMessage(content=text)],
        "human_notified": True,
        "pending_escalation": None,
        "_last_human_escalation_channels": channels,  # read by the API layer
    }


async def announce_new_tier(state: CoCState) -> dict:
    """The introduction for the tier just handed off to. Runs in the SAME turn
    as the handoff (not deferred to the next user message) so the customer sees
    the new persona introduce itself as part of the escalation moment, not after
    sending another message into the void."""
    from backend.config.loader import get_config
    from backend.graph.tiers.base import introduce

    persona = get_config().personas.get(state["current_tier"])
    return await introduce(state, persona)


async def do_handoff(state: CoCState) -> dict:
    """Perform the transition.

      1. summarize_for_handoff(messages, state["packet"], from, to, reason, ticket)
      2. current_tier = next_tier(current_tier)   <- the ONLY write to this field
      3. tier_just_changed = True, attempt_count = 0, pending_escalation = None
      4. stash a tier_change summary for the API layer to emit as an event

    Asserts the new tier index > old tier index before committing. Fails loudly
    rather than silently descalating — a silent descalation would look like a
    confusing UI bug and be miserable to track down.
    """
    from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage

    from backend.config.loader import get_config
    from backend.graph.handoff import summarize_for_handoff
    from backend.graph.state import reset_for_tier

    pending = state["pending_escalation"]
    if pending is None:
        msg = "do_handoff called with no pending_escalation"
        raise RuntimeError(msg)

    from_tier: Tier = pending["from_tier"]
    reason: str = pending["reason"]
    to_tier = next_tier(from_tier)

    if to_tier is None or ORDER.index(to_tier) <= ORDER.index(state["current_tier"]):
        msg = (
            f"Refusing to hand off from {from_tier} to {to_tier}: this would not "
            f"be a forward move from current_tier={state['current_tier']}. "
            f"Escalation must be monotonic."
        )
        raise RuntimeError(msg)

    new_packet = await summarize_for_handoff(
        state["messages"], state.get("packet"), from_tier, to_tier, reason, state["ticket_id"]
    )

    config = get_config()
    persona_from = config.personas.get(from_tier)
    persona_to = config.personas.get(to_tier)

    updates = reset_for_tier(state, to_tier)
    updates["packet"] = new_packet
    # The next tier's LLM context starts clean — it reasons over the handoff
    # packet, not the raw transcript. The frontend keeps its own running
    # transcript client-side, so nothing is lost for the customer.
    updates["messages"] = [RemoveMessage(id=REMOVE_ALL_MESSAGES)]
    updates["_last_tier_change"] = {
        "type": "tier_change",
        "from_tier": from_tier.value,
        "to_tier": to_tier.value,
        "from_persona": persona_from.name,
        "to_persona": persona_to.name,
        "theme": persona_to.theme,
        "reason": reason,
        "packet_summary": _summarize_packet_for_ui(new_packet),
    }
    counter_key = (
        "user_initiated_escalations"
        if pending.get("user_initiated")
        else "agent_initiated_escalations"
    )
    updates[counter_key] = state.get(counter_key, 0) + 1
    updates["escalation_reasons"] = [*state.get("escalation_reasons", []), reason]
    return updates


def build_graph() -> CompiledStateGraph:
    """Assemble the parent graph.

    Nodes:
      guardrail_input — input screening, Front Desk only (no-op elsewhere)
      classify   — UserIntent on each user turn
      front_desk / manager / vice_president / ceo  — the four subgraphs
      consent    — HITL interrupt for agent-initiated escalation
      context_request — HITL interrupt for a needed customer fact
      handoff    — summarize_for_handoff(), then advance the tier
      human      — CEO-tier human escalation; returns to the CEO, not END

    Compiled with MemorySaver for dev.
    TODO(M5+): Postgres checkpointer for anything real — MemorySaver loses
      every conversation on restart, including sessions paused at an interrupt.
    """
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.graph import END, StateGraph

    from backend.config.loader import get_config
    from backend.graph.tiers import ceo as ceo_tier
    from backend.graph.tiers import front_desk as front_desk_tier
    from backend.graph.tiers import manager as manager_tier
    from backend.graph.tiers import vice_president as vp_tier

    config = get_config()

    graph = StateGraph(CoCState)
    graph.add_node("guardrail_input", guardrail_input_node)
    graph.add_node("classify", classify_intent)
    graph.add_node(Tier.FRONT_DESK.value, front_desk_tier.build(config.models.front_desk))
    graph.add_node(Tier.MANAGER.value, manager_tier.build(config.models.manager))
    graph.add_node(Tier.VICE_PRESIDENT.value, vp_tier.build(config.models.vice_president))
    graph.add_node(Tier.CEO.value, ceo_tier.build(config.models.ceo))
    graph.add_node("consent", consent_node)
    graph.add_node("context_request", context_request_node)
    graph.add_node("handoff", do_handoff)
    # Registered as "introduce" (same name the tier subgraphs use internally)
    # so the API layer can detect an agent introduction with one check
    # regardless of whether it happened at session start or after a handoff.
    graph.add_node("introduce", announce_new_tier)
    graph.add_node("human", human_escalation_node)

    graph.set_entry_point("guardrail_input")
    graph.add_conditional_edges(
        "guardrail_input", route_from_guardrail, {"blocked": END, "continue": "classify"}
    )

    tier_map = {t.value: t.value for t in ORDER}
    graph.add_conditional_edges(
        "classify", route_from_classification, {**tier_map, "handoff": "handoff", "human": "human"}
    )

    for tier in ORDER:
        graph.add_conditional_edges(
            tier.value,
            route_from_tier,
            {
                "context_request": "context_request",
                "consent": "consent",
                "handoff": "handoff",
                "human": "human",
                "end": END,
            },
        )

    graph.add_conditional_edges("consent", route_from_consent, {"handoff": "handoff", "end": END})
    graph.add_conditional_edges("context_request", route_after_context, tier_map)
    graph.add_edge("handoff", "introduce")
    graph.add_edge("introduce", END)
    graph.add_edge("human", END)

    # Checkpointing round-trips Tier (a StrEnum) and HandoffPacket (a Pydantic
    # model) through msgpack. Both are simple, stable value types, so they're
    # explicitly allowlisted rather than left to trip the "unregistered type"
    # deprecation warning (and a future hard failure).
    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("backend.config.schema", "Tier"),
            ("backend.graph.handoff", "HandoffPacket"),
            ("backend.graph.handoff", "AttemptedAction"),
        ]
    )
    return graph.compile(checkpointer=MemorySaver(serde=serde))


# Escalation.max_attempts_per_tier is enforced in route_from_tier: once hit, the
#   supervisor stops asking for consent on every unresolved turn and hands off
#   directly. Without this a stubborn small model loops forever at the Front Desk.

# TODO(M5): emit one trace span per tier, all under a single ticket-level trace.
#   One trace per ticket, not per tier — the point is seeing the whole journey.
