"""Shared tier loop factory.  ⭐ WRITE THIS SECOND (right after handoff.py).

Every tier is this loop with different bindings. Writing the factory before any
individual tier is what stops the four tiers drifting into four bespoke
implementations that have to be maintained separately.

Each tier runs its own agentic loop:

    receive -> (introduce if just escalated) -> reason -> [call tools] ->
    [ask user for context if needed] -> respond OR request escalation
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from backend.config.schema import Persona, Tier, next_tier
from backend.graph.state import CoCState  # noqa: TC001 - needed at runtime for

# LangGraph's get_type_hints()-based schema inference on node/branch functions
# defined below; a TYPE_CHECKING-only import breaks add_conditional_edges.

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

    from backend.graph.handoff import HandoffPacket


class TierVerdict(BaseModel):
    """Structured output every tier produces alongside its reply.

    This is how a tier signals it is stuck without escalating itself — the
    supervisor reads the verdict and decides.
    """

    can_resolve: bool = Field(
        description="True if this tier fully answered the question with what it has. "
        "False if it lacks the knowledge, tools, or access to finish."
    )
    escalation_reason: str | None = Field(
        default=None,
        description="When can_resolve is False: the specific missing capability. "
        "Name the gap ('no access to billing records'), not a feeling.",
    )
    needs_context: str | None = Field(
        default=None,
        description="A question to ask the user before continuing (account number, "
        "order id, ...). Null when nothing is needed — the loop then runs "
        "uninterrupted. Do NOT ask just to confirm you understood.",
    )


BASE_SYSTEM_PROMPT = """\
You are {persona_name}, {persona_title} at {company_name}.

{capability_description}

{company_name} handles support for: {support_scope}.

You have been handed the following packet from earlier in this conversation. \
Do not ask the customer to repeat anything already listed under "Known facts", \
and do not re-attempt anything under "Already ruled out" — those are dead ends,
recorded so you do not walk into them again.

Customer's underlying goal: {customer_intent}

Known facts:
{verified_facts}

Already tried:
{attempted_actions}

Already ruled out (do not re-attempt):
{ruled_out}

Open questions:
{open_questions}

Instructions:
- If this is the first turn after a handoff, introduce yourself by name and \
title before anything else, and briefly acknowledge what you were handed so the \
customer knows they do not have to start over.
- Be honest about your limits. Saying "I can't do this from here" and offering \
to escalate is a good outcome, not a failure.
- Never promise something you cannot deliver.
"""


def _bulleted(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(none yet)"


def _actions_bulleted(actions: list) -> str:
    if not actions:
        return "(none yet)"
    return "\n".join(f"- [{a.tier}] {a.action} -> {a.outcome}" for a in actions)


def render_system_prompt(
    persona: Persona,
    company_name: str,
    support_scope: list[str],
    capability_description: str,
    packet: HandoffPacket,
) -> str:
    """Render BASE_SYSTEM_PROMPT for one tier turn. Nothing here is hardcoded —
    persona name/title and company facts all come from config."""
    return BASE_SYSTEM_PROMPT.format(
        persona_name=persona.name,
        persona_title=persona.title,
        company_name=company_name,
        capability_description=capability_description.strip(),
        support_scope=", ".join(support_scope) if support_scope else "general support",
        customer_intent=packet.customer_intent or "(not yet established)",
        verified_facts=_bulleted(packet.verified_facts),
        attempted_actions=_actions_bulleted(packet.attempted_actions),
        ruled_out=_bulleted(packet.ruled_out),
        open_questions=_bulleted(packet.open_questions),
    )


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def make_model(model_id: str, tools: list[BaseTool], temperature: float = 0.3):  # noqa: ANN201
    """ChatOllama bound to `tools`.

    If `tools` is empty, return the model UNBOUND — do not call .bind_tools([]).
    Some providers treat an empty tool list differently from no tool list at all,
    and the whole Front Desk guarantee rests on this distinction.

    Structured-output / classification callers should pass temperature=0 —
    small local models need determinism to hold a decision boundary reliably.
    """
    from langchain_ollama import ChatOllama

    model = ChatOllama(model=model_id, base_url=_ollama_base_url(), temperature=temperature)
    if tools:
        return model.bind_tools(tools)
    return model


async def introduce(state: CoCState, persona: Persona) -> dict:
    """The self-introduction, emitted on every tier change.

    Acknowledges the handoff rather than restarting the conversation — the
    customer has already explained themselves once. References the packet's
    customer_intent so the introduction demonstrates the handoff worked.
    """
    from langchain_core.messages import AIMessage

    packet = state["packet"]
    if packet.customer_intent:
        text = (
            f"Hi, I'm {persona.name}, {persona.title}. I've been briefed on your "
            f"issue — {packet.customer_intent} — and I'm ready to pick up from here."
        )
    else:
        text = f"Hi, I'm {persona.name}, {persona.title}. How can I help?"
    return {"messages": [AIMessage(content=text)], "tier_just_changed": False}


def build_tier(
    tier: Tier,
    persona: Persona,
    model_id: str,
    tools: list[BaseTool],
    capability_description: str,
) -> CompiledStateGraph:
    """Build one tier's compiled subgraph.

    Nodes:
      introduce  — only when state["tier_just_changed"]; streams the self-intro,
                   then clears the flag.
      agent      — the model call. Tools bound ONLY if `tools` is non-empty.
      tools      — ToolNode. NOT ADDED AT ALL when `tools` is empty.
      verdict    — structured TierVerdict; sets pending_escalation when stuck.

    Edges: introduce -> agent -> (tools -> agent)* -> verdict -> END

    ⚠ INVARIANT: when `tools` is empty, this builds a graph with NO tool node
      and NO tools bound to the model. Not a filtered registry — an absent one.
      The Front Desk has no runtime path to a tool call, so no prompt can talk
      it into one.

    TODO(M3): the VP tier needs concurrent tool execution — asyncio.gather over
      independent calls rather than sequential ToolNode dispatch. Add it here
      behind a flag so all tiers benefit, rather than forking vice_president.py.
    """
    from langchain_core.messages import SystemMessage
    from langgraph.graph import END, StateGraph
    from langgraph.prebuilt import ToolNode

    from backend.config.loader import get_config

    has_tools = bool(tools)
    agent_model = make_model(model_id, tools)
    # The verdict call is a separate, unbound structured-output call — it must
    # never itself be able to trigger a tool call. temperature=0: this is a
    # decision, not a generation, and small models need determinism to hold it.
    verdict_model = make_model(model_id, [], temperature=0).with_structured_output(TierVerdict)

    def _company():
        return get_config().company

    async def introduce_node(state: CoCState) -> dict:
        if state.get("tier_just_changed"):
            return await introduce(state, persona)
        return {}

    async def agent_node(state: CoCState) -> dict:
        company = _company()
        prompt = render_system_prompt(
            persona, company.name, company.support_scope, capability_description, state["packet"]
        )
        messages = [SystemMessage(content=prompt), *state["messages"]]
        response = await agent_model.ainvoke(messages)
        return {"messages": [response]}

    def route_after_agent(state: CoCState) -> str:
        last = state["messages"][-1]
        if has_tools and getattr(last, "tool_calls", None):
            return "tools"
        return "verdict"

    async def verdict_node(state: CoCState) -> dict:
        company = _company()
        prompt = render_system_prompt(
            persona, company.name, company.support_scope, capability_description, state["packet"]
        )
        prompt += (
            "\n\nBased on the conversation so far, decide: did you fully resolve "
            "the customer's request with what you have access to? If not, name "
            "the specific missing capability. If you need one specific fact from "
            "the customer to continue, ask for exactly that."
        )
        messages = [SystemMessage(content=prompt), *state["messages"]]
        verdict: TierVerdict = await verdict_model.ainvoke(messages)

        updates: dict = {"pending_context_question": verdict.needs_context or None}

        if verdict.can_resolve:
            updates["pending_escalation"] = None
        elif state.get("escalation_declined"):
            # The customer just declined this exact escalation — do not
            # immediately re-propose it on the very next turn. Keep working at
            # this tier; a later turn can ask again once the decline has aged out.
            updates["attempt_count"] = state.get("attempt_count", 0) + 1
            updates["pending_escalation"] = None
            updates["escalation_declined"] = False
        else:
            target = next_tier(tier)
            updates["attempt_count"] = state.get("attempt_count", 0) + 1
            updates["pending_escalation"] = {
                "from_tier": tier,
                "to_tier": target if target is not None else tier,
                "reason": verdict.escalation_reason or "unable to resolve at this tier",
                "user_initiated": False,
            }
        return updates

    graph = StateGraph(CoCState)
    graph.add_node("introduce", introduce_node)
    graph.add_node("agent", agent_node)
    graph.add_node("verdict", verdict_node)
    graph.set_entry_point("introduce")
    graph.add_edge("introduce", "agent")

    if has_tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_conditional_edges(
            "agent", route_after_agent, {"tools": "tools", "verdict": "verdict"}
        )
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", "verdict")

    graph.add_edge("verdict", END)

    return graph.compile()
